"""
title: Context Compiler Pipe
author: rlippmann
author_url: https://github.com/rlippmann/context-compiler
funding_url: https://github.com/rlippmann/context-compiler
version: 0.8.2
requirements: context-compiler>=0.6.14

Minimal Open WebUI Pipe integration for Context Compiler.

This integration demonstrates mapping Context Compiler `Decision` output into
Open WebUI request flow.

Scope is intentionally limited:
- Single Pipe Function for Open WebUI v0.7.2.
- In-memory per-process engine map keyed by chat key.
- No persistence, no multi-worker coordination, no external storage.
"""

import inspect
import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any, cast

from fastapi import Request  # type: ignore[import-not-found]
from open_webui.models.users import Users  # type: ignore[import-not-found]
from open_webui.utils.chat import generate_chat_completion  # type: ignore[import-not-found]

try:
    from pydantic import BaseModel, Field
except ModuleNotFoundError:
    # Keep this import optional: CI/tests run without integration extras.
    # These lightweight fallbacks keep import-time behavior deterministic so
    # coverage exercises the pipe module without pydantic installed.
    class BaseModel:  # type: ignore[no-redef]
        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    def Field(*, default: Any, description: str = "") -> Any:  # type: ignore[no-redef]
        del description
        return default


from context_compiler import State, create_engine, get_policy_items, get_premise_value
from context_compiler.engine import Engine

logger = logging.getLogger(__name__)

_CC_MARKER = "[[cc_state]]"
_ENGINES_BY_CHAT_KEY: dict[str, Engine] = {}
# Example-only in-memory checkpoint store.
# This keeps continuation state only for the current process lifetime.
# Real deployments should persist checkpoints externally (DB/Redis/etc.),
# or restart continuity for pending flows will be lost.
_CHECKPOINTS_BY_CHAT_KEY: dict[str, str] = {}


def _resolve_chat_key(
    user: dict[str, Any],
    chat_id: str | None,
    metadata: dict[str, Any] | None,
) -> str:
    """Resolve chat key from reserved args with a minimal fallback.

    Resolution order:
    1. ``__chat_id__``
    2. ``__metadata__["chat_id"]``
    3. ``no-chat-id:<user_id>``

    The fallback key is a degraded convenience for this minimal integration and
    is not a strong chat-isolation guarantee.
    """
    if chat_id:
        return chat_id
    if isinstance(metadata, dict):
        metadata_chat_id = metadata.get("chat_id")
        if isinstance(metadata_chat_id, str) and metadata_chat_id:
            return metadata_chat_id
    user_id = str(user["id"])
    return f"no-chat-id:{user_id}"


def _extract_latest_user_text(messages: list[dict[str, Any]]) -> str | None:
    """Return latest plain-text user content, scanning from the end.

    Uses the last message with ``role == "user"``. Only plain string content is
    eligible for compilation. Non-text or missing-user cases return ``None`` so
    the caller can bypass compiler behavior.
    """
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        return None
    return None


def _render_compiler_state_block(state: State) -> str:
    """Render deterministic compiler-owned state block text.

    The first line is ``[[cc_state]]``. Optional lines follow for ``Premise``,
    ``Use``, and ``Prohibit``. Policy items are rendered alphabetically, and
    identical state must produce identical output bytes.
    """
    lines: list[str] = [_CC_MARKER]

    premise = get_premise_value(state)
    if premise is not None:
        lines.append(f"Premise: {premise}")

    use_items = sorted(get_policy_items(state, "use"))
    if use_items:
        lines.append("Use: " + ", ".join(use_items))

    prohibit_items = sorted(get_policy_items(state, "prohibit"))
    if prohibit_items:
        lines.append("Prohibit: " + ", ".join(prohibit_items))

    return "\n".join(lines)


def _replace_compiler_system_message(
    messages: list[dict[str, Any]],
    rendered_state_block: str,
) -> list[dict[str, Any]]:
    """Replace compiler-owned state messages while preserving other order.

    Compiler-owned messages are identified by ``[[cc_state]]`` prefix. Existing
    compiler-owned system messages are removed, and one fresh compiler-owned
    system message is inserted after the last remaining system message, else at
    index ``0``. Relative order of non-compiler messages is preserved.

    Invariant: exactly one compiler-owned state message exists afterward.
    """
    filtered_messages: list[dict[str, Any]] = []
    last_system_index = -1

    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role == "system" and isinstance(content, str) and content.startswith(_CC_MARKER):
            continue

        filtered_messages.append(message)
        if role == "system":
            last_system_index = len(filtered_messages) - 1

    insert_at = last_system_index + 1 if last_system_index >= 0 else 0
    compiler_message: dict[str, Any] = {"role": "system", "content": rendered_state_block}
    return [
        *filtered_messages[:insert_at],
        compiler_message,
        *filtered_messages[insert_at:],
    ]


def _normalize_state(value: object) -> State:
    if isinstance(value, dict):
        return cast(State, value)
    return {"premise": None, "policies": {}, "version": 2}


def _active_state_summary(state: object) -> str:
    normalized = _normalize_state(state)
    premise = get_premise_value(normalized)
    use_items = sorted(get_policy_items(normalized, "use"))
    prohibit_items = sorted(get_policy_items(normalized, "prohibit"))
    parts: list[str] = []
    if premise is not None:
        parts.append(f'premise="{premise}"')
    if use_items:
        parts.append("use " + ", ".join(use_items))
    if prohibit_items:
        parts.append("prohibit " + ", ".join(prohibit_items))
    return "; ".join(parts) if parts else "none"


def _compact_state_change(before: object, after: object) -> str:
    before_state = _normalize_state(before)
    after_state = _normalize_state(after)
    before_premise = get_premise_value(before_state)
    after_premise = get_premise_value(after_state)
    before_use = set(get_policy_items(before_state, "use"))
    after_use = set(get_policy_items(after_state, "use"))
    before_prohibit = set(get_policy_items(before_state, "prohibit"))
    after_prohibit = set(get_policy_items(after_state, "prohibit"))

    parts: list[str] = []
    if before_premise != after_premise:
        if after_premise is None:
            parts.append("-premise")
        elif before_premise is None:
            parts.append(f'+premise "{after_premise}"')
        else:
            parts.append(f'~premise "{after_premise}"')
    for item in sorted(after_use - before_use):
        parts.append(f"+use {item}")
    for item in sorted(before_use - after_use):
        parts.append(f"-use {item}")
    for item in sorted(after_prohibit - before_prohibit):
        parts.append(f"+prohibit {item}")
    for item in sorted(before_prohibit - after_prohibit):
        parts.append(f"-prohibit {item}")
    return ", ".join(parts) if parts else "none"


def _build_compact_trace_text(
    *,
    decision: object,
    state_before: object,
    state_after: object,
    llm_called: bool,
    state_injected: str,
) -> str:
    kind_obj = decision.get("kind") if isinstance(decision, dict) else None
    kind = kind_obj if isinstance(kind_obj, str) else "unknown"
    lines = ["Context Compiler trace", "", f"decision kind: {kind}"]

    if kind == "update":
        lines.append(f"state change: {_compact_state_change(state_before, state_after)}")
        lines.append(f"active state: {_active_state_summary(state_after)}")
        lines.append(f"downstream LLM call: {'yes' if llm_called else 'no'}")
        lines.append("")
        lines.append(f"state injected: {state_injected}")
        return "\n".join(lines)

    if kind == "clarify":
        prompt_obj = decision.get("prompt_to_user") if isinstance(decision, dict) else None
        prompt = prompt_obj if isinstance(prompt_obj, str) else ""
        lines.append(f"clarification prompt: {prompt}")
        lines.append(f"active state: {_active_state_summary(state_after)}")
        lines.append(f"downstream LLM call: {'yes' if llm_called else 'no'}")
        lines.append("state injected: no")
        return "\n".join(lines)

    lines.append(f"active state: {_active_state_summary(state_after)}")
    lines.append(f"downstream LLM call: {'yes' if llm_called else 'no'}")
    lines.append("state injected: no")
    return "\n".join(lines)


def _strip_trace_block_from_text(content: str) -> str:
    marker = "Context Compiler trace"
    index = content.find(marker)
    if index < 0:
        return content
    return content[:index].rstrip()


def _strip_trace_blocks_from_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for message in messages:
        msg = dict(message)
        content = msg.get("content")
        if isinstance(content, str):
            msg["content"] = _strip_trace_block_from_text(content)
        cleaned.append(msg)
    return cleaned


def _strip_existing_trace_from_chunk(chunk: object) -> object:
    if isinstance(chunk, str):
        return _strip_trace_block_from_text(chunk)
    if isinstance(chunk, bytes):
        decoded = chunk.decode("utf-8", errors="ignore")
        cleaned = _strip_trace_block_from_text(decoded)
        return cleaned.encode("utf-8")
    return chunk


def _render_item_label(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _near_miss_directive_clarify(value: str) -> str | None:
    normalized = re.sub(r"\s+", " ", value.strip())
    lower = normalized.lower()

    if lower in {"reset premise", "reset premises", "clear premises"}:
        return "Unknown directive.\nUse 'clear premise' or 'reset policies'."
    if lower.startswith("set premise to "):
        return "Invalid premise syntax.\nUse 'set premise <value>'."
    if lower.startswith("change premise ") and not lower.startswith("change premise to "):
        return "Invalid premise syntax.\nUse 'change premise to <value>'."
    return None


def _summarize_update_from_input(user_input: str) -> str:
    normalized = re.sub(r"\s+", " ", user_input.strip())
    lower = normalized.lower()

    if lower == "clear state":
        return "State cleared."
    if lower == "clear premise":
        return "Premise cleared."
    if lower == "reset policies":
        return "Policies reset."

    replacement_match = re.match(
        r"^use\s+(.+?)\s+instead\s+of\s+(.+)$", normalized, flags=re.IGNORECASE
    )
    if replacement_match is not None:
        item = _render_item_label(replacement_match.group(1).rstrip(" .!?"))
        if item:
            return f"State updated: Use {item}."

    use_match = re.match(r"^use\s+(.+)$", normalized, flags=re.IGNORECASE)
    if use_match is not None:
        item = _render_item_label(use_match.group(1).rstrip(" .!?"))
        if item:
            return f"State updated: Use {item}."

    prohibit_match = re.match(r"^prohibit\s+(.+)$", normalized, flags=re.IGNORECASE)
    if prohibit_match is not None:
        item = _render_item_label(prohibit_match.group(1).rstrip(" .!?"))
        if item:
            return f"State updated: Prohibit {item}."

    remove_policy_match = re.match(r"^remove\s+policy\s+(.+)$", normalized, flags=re.IGNORECASE)
    if remove_policy_match is not None:
        item = _render_item_label(remove_policy_match.group(1).rstrip(" .!?"))
        if item:
            return f"State updated: Removed policy {item}."

    return "State updated."


def _is_administrative_update_input(user_input: str) -> bool:
    normalized = re.sub(r"\s+", " ", user_input.strip()).lower()
    return (
        normalized == "clear state"
        or normalized == "clear premise"
        or normalized == "reset policies"
        or normalized.startswith("remove policy ")
    )


class Pipe:
    """Map Context Compiler decisions into Open WebUI pipe behavior.

    - ``clarify`` returns plain text and skips model forwarding.
    - ``passthrough`` forwards with minimal mutation.
    - ``update`` forwards with compiler-owned state injection.
    """

    class Valves(BaseModel):
        BASE_MODEL_ID: str = Field(
            default="",
            description=(
                "Required Open WebUI model id used for forwarding. Must exactly match a "
                "configured model id in Open WebUI (not arbitrary text), for example: "
                "llama3.1:8b."
            ),
        )
        SHOW_CONTEXT_COMPILER_TRACE: bool = Field(
            default=False,
            description="Include concise Context Compiler trace text in responses.",
        )

    def __init__(self) -> None:
        self.valves = self.Valves()

    def _is_model_not_found_text(self, value: object) -> bool:
        if not isinstance(value, str):
            return False
        return "model not found" in value.lower()

    def _contains_model_not_found(self, value: object) -> bool:
        if self._is_model_not_found_text(value):
            return True
        if isinstance(value, dict):
            return any(self._contains_model_not_found(v) for v in value.values())
        if isinstance(value, list):
            return any(self._contains_model_not_found(v) for v in value)
        return False

    def _normalize_forward_error(self, response: Any) -> str | None:
        if self._contains_model_not_found(response):
            return (
                "Context Compiler pipe misconfigured: BASE_MODEL_ID is invalid or not "
                "configured in Open WebUI. Configure a valid model id in "
                "Admin Panel → Settings → Models."
            )
        return None

    def _normalize_forward_exception(self, exc: Exception) -> str | None:
        detail = getattr(exc, "detail", None)
        if self._contains_model_not_found(detail) or self._contains_model_not_found(str(exc)):
            return (
                "Context Compiler pipe misconfigured: BASE_MODEL_ID is invalid or not "
                "configured in Open WebUI. Configure a valid model id in "
                "Admin Panel → Settings → Models."
            )
        return None

    def _trace_enabled(self) -> bool:
        return bool(getattr(self.valves, "SHOW_CONTEXT_COMPILER_TRACE", False))

    def _append_trace_to_response(self, response: Any, trace_text: str) -> Any:
        body_iterator = getattr(response, "body_iterator", None)
        if body_iterator is not None and callable(getattr(body_iterator, "__aiter__", None)):
            response.body_iterator = self._append_trace_to_stream(
                cast(AsyncIterator[object], body_iterator), trace_text
            )
            return response
        aiter = getattr(response, "__aiter__", None)
        if callable(aiter):
            return self._append_trace_to_stream(cast(AsyncIterator[object], response), trace_text)
        if isinstance(response, str):
            cleaned = _strip_trace_block_from_text(response)
            return f"{cleaned}\n\n{trace_text}"
        if isinstance(response, dict):
            choices = response.get("choices")
            if isinstance(choices, list) and choices:
                first = choices[0]
                if isinstance(first, dict):
                    message = first.get("message")
                    if isinstance(message, dict):
                        content = message.get("content")
                        if isinstance(content, str):
                            cleaned = _strip_trace_block_from_text(content)
                            message["content"] = f"{cleaned}\n\n{trace_text}"
                            return response
        choices_attr = getattr(response, "choices", None)
        if isinstance(choices_attr, list) and choices_attr:
            first_choice = choices_attr[0]
            message_attr = getattr(first_choice, "message", None)
            content_attr = getattr(message_attr, "content", None)
            if message_attr is not None and isinstance(content_attr, str):
                cleaned = _strip_trace_block_from_text(content_attr)
                message_attr.content = f"{cleaned}\n\n{trace_text}"
                return response
        return response

    def _append_trace_to_stream(
        self, stream: AsyncIterator[object], trace_text: str
    ) -> AsyncIterator[object]:
        async def _wrapped() -> AsyncIterator[object]:
            chunk_type: type[str] | type[bytes] | None = None
            saw_done = False
            trace_json = json.dumps({"choices": [{"delta": {"content": f"\n\n{trace_text}"}}]})
            trace_event = f"data: {trace_json}\n\n"

            def _matches_done(value: str) -> bool:
                normalized = value.strip()
                return normalized == "data: [DONE]" or normalized == "[DONE]"

            async for chunk in stream:
                if chunk_type is None:
                    if isinstance(chunk, bytes):
                        chunk_type = bytes
                    elif isinstance(chunk, str):
                        chunk_type = str
                if isinstance(chunk, bytes):
                    decoded = chunk.decode("utf-8", errors="ignore")
                    if _matches_done(decoded):
                        saw_done = True
                        yield trace_event.encode("utf-8")
                        yield chunk
                        continue
                elif isinstance(chunk, str) and _matches_done(chunk):
                    saw_done = True
                    yield trace_event
                    yield chunk
                    continue
                yield _strip_existing_trace_from_chunk(chunk)
            if saw_done:
                return
            suffix = f"\n\n{trace_text}"
            if chunk_type is bytes:
                yield suffix.encode("utf-8")
            else:
                yield suffix

        return _wrapped()

    def _with_trace(
        self,
        response: Any,
        *,
        original_input: str,
        compiler_input: str,
        decision: object,
        state_before: object,
        state_after: object,
        llm_called: bool,
        preprocessor_output: str | None = None,
        state_injected: str = "no",
    ) -> Any:
        if not self._trace_enabled():
            return response
        del original_input, compiler_input, preprocessor_output
        trace_text = _build_compact_trace_text(
            decision=decision,
            state_before=state_before,
            state_after=state_after,
            llm_called=llm_called,
            state_injected=state_injected,
        )
        return self._append_trace_to_response(response, trace_text)

    async def _forward_passthrough(
        self,
        body: dict[str, Any],
        user_payload: dict[str, Any],
        request: Request,
    ) -> Any:
        """Forward with a shallow body copy and model override only."""
        payload = {**body}
        payload["model"] = self.valves.BASE_MODEL_ID
        raw_messages = body.get("messages")
        if isinstance(raw_messages, list):
            payload["messages"] = _strip_trace_blocks_from_messages(
                [msg for msg in raw_messages if isinstance(msg, dict)]
            )
        user = Users.get_user_by_id(user_payload["id"])
        if inspect.isawaitable(user):
            user = await user
        try:
            response = await generate_chat_completion(request, payload, user)
        except Exception as exc:
            normalized_exception = self._normalize_forward_exception(exc)
            if normalized_exception is not None:
                return normalized_exception
            raise
        normalized_error = self._normalize_forward_error(response)
        if normalized_error is not None:
            return normalized_error
        return response

    async def _forward_update(
        self,
        body: dict[str, Any],
        user_payload: dict[str, Any],
        request: Request,
        state: State,
    ) -> Any:
        """Forward with one compiler-owned state message based on current state.

        The body is shallow-copied, ``model`` is overridden, and exactly one
        compiler-owned message is inserted/replaced before forwarding.
        """
        payload = {**body}
        payload["model"] = self.valves.BASE_MODEL_ID

        raw_messages = body.get("messages")
        messages = (
            _strip_trace_blocks_from_messages(
                [msg for msg in raw_messages if isinstance(msg, dict)]
            )
            if isinstance(raw_messages, list)
            else []
        )
        payload["messages"] = _replace_compiler_system_message(
            messages,
            _render_compiler_state_block(state),
        )

        user = Users.get_user_by_id(user_payload["id"])
        if inspect.isawaitable(user):
            user = await user
        try:
            response = await generate_chat_completion(request, payload, user)
        except Exception as exc:
            normalized_exception = self._normalize_forward_exception(exc)
            if normalized_exception is not None:
                return normalized_exception
            raise
        normalized_error = self._normalize_forward_error(response)
        if normalized_error is not None:
            return normalized_error
        return response

    async def pipe(
        self,
        body: dict[str, Any],
        __user__: dict[str, Any],
        __request__: Request,
        __chat_id__: str | None = None,
        __metadata__: dict[str, Any] | None = None,
    ) -> Any:
        """Run minimal host flow around compiler decisions.

        Flow:
        - Extract latest user text.
        - Bypass compiler for non-text or missing-user turns.
        - Resolve chat key and get/create per-chat engine.
        - Call ``engine.step(...)``.
        - Map ``clarify`` / ``passthrough`` / ``update`` outcomes.
        """
        raw_messages = body.get("messages")
        messages = (
            [msg for msg in raw_messages if isinstance(msg, dict)]
            if isinstance(raw_messages, list)
            else []
        )
        base_model_id = self.valves.BASE_MODEL_ID.strip()
        current_model_id = str(body.get("model", "")).strip()
        if not base_model_id:
            return "Context Compiler pipe misconfigured: BASE_MODEL_ID is required."
        if current_model_id and base_model_id == current_model_id:
            return (
                "Context Compiler pipe misconfigured: BASE_MODEL_ID must not match "
                "the selected pipe model id to avoid recursive routing."
            )

        latest_user_text = _extract_latest_user_text(messages)
        logger.debug("pipe: user_input_found=%s", latest_user_text is not None)

        if latest_user_text is None:
            return await self._forward_passthrough(body, __user__, __request__)

        chat_key = _resolve_chat_key(__user__, __chat_id__, __metadata__)
        engine = _ENGINES_BY_CHAT_KEY.get(chat_key)
        if engine is None:
            engine = create_engine()
            checkpoint = _CHECKPOINTS_BY_CHAT_KEY.get(chat_key)
            if checkpoint is not None:
                engine.import_checkpoint_json(checkpoint)
            _ENGINES_BY_CHAT_KEY[chat_key] = engine

        state_before = engine.state
        logger.debug("pipe: engine_input=%r", latest_user_text)
        decision = engine.step(latest_user_text)
        kind = decision["kind"]
        logger.debug("pipe: decision=%s", kind)
        near_miss_prompt = _near_miss_directive_clarify(latest_user_text)
        state_after = decision.get("state") if isinstance(decision, dict) else None
        if state_after is None:
            state_after = engine.state

        if kind == "clarify":
            _CHECKPOINTS_BY_CHAT_KEY[chat_key] = engine.export_checkpoint_json()
            return self._with_trace(
                near_miss_prompt or decision["prompt_to_user"] or "",
                original_input=latest_user_text,
                compiler_input=latest_user_text,
                decision=decision,
                state_before=state_before,
                state_after=state_after,
                llm_called=False,
            )
        if near_miss_prompt is not None and kind == "passthrough":
            return self._with_trace(
                near_miss_prompt,
                original_input=latest_user_text,
                compiler_input=latest_user_text,
                decision={"kind": "clarify", "prompt_to_user": near_miss_prompt},
                state_before=state_before,
                state_after=state_after,
                llm_called=False,
            )
        if kind == "passthrough":
            response = await self._forward_passthrough(body, __user__, __request__)
            return self._with_trace(
                response,
                original_input=latest_user_text,
                compiler_input=latest_user_text,
                decision=decision,
                state_before=state_before,
                state_after=state_after,
                llm_called=True,
            )
        if kind == "update":
            _CHECKPOINTS_BY_CHAT_KEY[chat_key] = engine.export_checkpoint_json()
            if _is_administrative_update_input(latest_user_text):
                return self._with_trace(
                    _summarize_update_from_input(latest_user_text),
                    original_input=latest_user_text,
                    compiler_input=latest_user_text,
                    decision=decision,
                    state_before=state_before,
                    state_after=state_after,
                    llm_called=False,
                )
            response = await self._forward_update(
                body,
                __user__,
                __request__,
                state_after,
            )
            return self._with_trace(
                response,
                original_input=latest_user_text,
                compiler_input=latest_user_text,
                decision=decision,
                state_before=state_before,
                state_after=state_after,
                llm_called=True,
                state_injected=_active_state_summary(state_after),
            )

        response = await self._forward_passthrough(body, __user__, __request__)
        return self._with_trace(
            response,
            original_input=latest_user_text,
            compiler_input=latest_user_text,
            decision=decision,
            state_before=state_before,
            state_after=state_after,
            llm_called=True,
        )
