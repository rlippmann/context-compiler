"""
title: Context Compiler Pipe (Preprocessor)
author: rlippmann
author_url: https://github.com/rlippmann/context-compiler
funding_url: https://github.com/rlippmann/context-compiler
version: 0.9.2
requirements: context-compiler[experimental]>=0.7.4

Open WebUI integration with Context Compiler preprocessor.

This example extends `open_webui_pipe.py` by inserting a preprocessing step:

1. Run heuristic preprocessor (fast, high-precision cases)
2. Fall back to Open WebUI-native model completion when needed
3. Pass resulting directive (or original input) to `engine.step(...)`

Core decision handling remains the same as the base integration.
"""

import inspect
import json
import logging
import re
from collections.abc import AsyncIterator
from importlib.resources import as_file, files
from importlib.resources.abc import Traversable
from typing import Any, Literal, cast

from fastapi import Request  # type: ignore[import-not-found]
from open_webui.models.users import Users  # type: ignore[import-not-found]
from open_webui.utils.chat import generate_chat_completion  # type: ignore[import-not-found]
from open_webui.utils.models import get_all_models  # type: ignore[import-not-found]

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


from context_compiler import (
    DECISION_CLARIFY,
    DECISION_PASSTHROUGH,
    DECISION_UPDATE,
    POLICY_PROHIBIT,
    POLICY_USE,
    State,
    create_engine,
    get_clarify_prompt,
    get_decision_state,
    get_policy_items,
    get_premise_value,
    is_clarify,
    is_passthrough,
    is_update,
)
from context_compiler.engine import Engine
from context_compiler.observability import build_compact_trace_text
from experimental.preprocessor import (
    PREPROCESS_OUTCOME_DIRECTIVE,
    parse_preprocessor_output,
    preprocess_heuristic,
    render_prompt,
)

logger = logging.getLogger(__name__)

_CC_MARKER = "[[cc_state]]"
_ENGINES_BY_CHAT_KEY: dict[str, Engine] = {}
# Example-only in-memory checkpoint store.
# This keeps continuation state only for the current process lifetime.
# Real deployments should persist checkpoints externally (DB/Redis/etc.),
# or restart continuity for pending flows will be lost.
_CHECKPOINTS_BY_CHAT_KEY: dict[str, str] = {}
_PROMPTS_DIR = files("experimental.preprocessor").joinpath("prompts")


def _is_directive_shaped_input(message: str) -> bool:
    normalized = re.sub(r"\s+", " ", message.strip()).lower()
    return (
        normalized.startswith("use")
        or normalized.startswith("prohibit")
        or normalized.startswith("remove policy")
        or normalized.startswith("set premise")
        or normalized.startswith("change premise")
        or normalized.startswith("clear")
        or normalized.startswith("reset")
    )


def _prompt_file_path(profile: str) -> Traversable:
    # Runtime prompt selection for fallback precompilation:
    # - default: most instruction-following models
    # - llama: models that need tighter prompt guidance
    if profile == "llama":
        return _PROMPTS_DIR.joinpath("llama.txt")
    return _PROMPTS_DIR.joinpath("default.txt")


def _resolve_chat_key(
    user: dict[str, Any],
    chat_id: str | None,
    metadata: dict[str, Any] | None,
) -> str:
    if chat_id:
        return chat_id
    if isinstance(metadata, dict):
        metadata_chat_id = metadata.get("chat_id")
        if isinstance(metadata_chat_id, str) and metadata_chat_id:
            return metadata_chat_id
    user_id = str(user["id"])
    return f"no-chat-id:{user_id}"


def _extract_latest_user_text(messages: list[dict[str, Any]]) -> str | None:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        return None
    return None


def _has_pending_clarification(engine: Engine) -> bool:
    return engine.has_pending_clarification()


def _render_compiler_state_block(state: State) -> str:
    lines: list[str] = [_CC_MARKER]

    premise = get_premise_value(state)
    if premise is not None:
        lines.append(f"Premise: {premise}")

    use_items = sorted(get_policy_items(state, POLICY_USE))
    if use_items:
        lines.append("Use: " + ", ".join(use_items))

    prohibit_items = sorted(get_policy_items(state, POLICY_PROHIBIT))
    if prohibit_items:
        lines.append("Prohibit: " + ", ".join(prohibit_items))

    return "\n".join(lines)


def _render_show_state_summary(engine: Engine) -> str:
    premise = get_premise_value(engine.state)
    use_items = sorted(get_policy_items(engine.state, POLICY_USE))
    prohibit_items = sorted(get_policy_items(engine.state, POLICY_PROHIBIT))
    pending = engine.has_pending_clarification()

    use_text = ", ".join(use_items) if use_items else "none"
    prohibit_text = ", ".join(prohibit_items) if prohibit_items else "none"
    premise_text = premise if premise is not None else "none"
    pending_text = "yes" if pending else "no"

    return (
        f"Premise: {premise_text}\n"
        f"Use: {use_text}\n"
        f"Prohibit: {prohibit_text}\n"
        f"Pending clarification: {pending_text}"
    )


def _replace_compiler_system_message(
    messages: list[dict[str, Any]],
    rendered_state_block: str,
) -> list[dict[str, Any]]:
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


def _has_non_empty_authoritative_state(state: State) -> bool:
    if get_premise_value(state) is not None:
        return True
    return bool(get_policy_items(state, POLICY_USE) or get_policy_items(state, POLICY_PROHIBIT))


def _build_compact_trace_text(
    *,
    decision: object,
    state_before: object,
    state_after: object,
    llm_called: bool,
    state_injected: str,
) -> str:
    return build_compact_trace_text(
        decision=decision,
        state_before=state_before,
        state_after=state_after,
        llm_called=llm_called,
        state_injected=state_injected,
    )


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


def _build_forward_messages(
    raw_messages: object,
    *,
    state: State | None = None,
) -> list[dict[str, Any]]:
    """Build forwarded messages with trace stripping and optional state injection."""
    messages = (
        _strip_trace_blocks_from_messages([msg for msg in raw_messages if isinstance(msg, dict)])
        if isinstance(raw_messages, list)
        else []
    )
    if state is not None and _has_non_empty_authoritative_state(state):
        return _replace_compiler_system_message(
            messages,
            _render_compiler_state_block(state),
        )
    return messages


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


def _extract_completion_content(response: object) -> str | None:
    choices_attr = getattr(response, "choices", None)
    if isinstance(choices_attr, list) and choices_attr:
        first_choice = choices_attr[0]
        message_attr = getattr(first_choice, "message", None)
        content_attr = getattr(message_attr, "content", None)
        if isinstance(content_attr, str):
            return content_attr

    if isinstance(response, dict):
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                message = first_choice.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content

    return None


def _normalize_model_id(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _is_truthy_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "on"}:
            return True
        if normalized in {"false", "0", "off"}:
            return False
    return False


class Pipe:
    """Map Context Compiler decisions into Open WebUI pipe behavior.

    This variant adds a preprocessor stage before ``engine.step(...)``:
    heuristic first, then Open WebUI-native LLM fallback.
    Update decisions return deterministic local acknowledgement (no model call).
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
        PREPROCESSOR_MODEL_ID: str | None = Field(
            default=None,
            description=(
                "Optional model id for fallback precompilation (defaults to BASE_MODEL_ID)."
            ),
        )
        PREPROCESSOR_PROMPT_PROFILE: Literal["default", "llama"] = Field(
            default="default",
            description="Prompt profile for LLM fallback precompilation.",
        )
        ALLOW_MISSING_BASE_MODEL_FOR_DEBUG: bool = Field(
            default=False,
            description="Allow missing BASE_MODEL_ID for debug/testing only.",
        )
        SHOW_CONTEXT_COMPILER_TRACE: bool = Field(
            default=False,
            description="Include concise Context Compiler trace text in responses.",
        )

    def __init__(self) -> None:
        self.valves = self.Valves()

    def _allow_missing_base_model_for_debug(self) -> bool:
        return _is_truthy_bool(getattr(self.valves, "ALLOW_MISSING_BASE_MODEL_FOR_DEBUG", False))

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

    def _normalize_preprocessor_error(self, response: Any) -> str | None:
        if self._contains_model_not_found(response):
            return (
                "Context Compiler pipe misconfigured: PREPROCESSOR_MODEL_ID is invalid or "
                "not configured in Open WebUI. Configure a valid model id in "
                "Admin Panel → Settings → Models."
            )
        return None

    def _normalize_preprocessor_exception(self, exc: Exception) -> str | None:
        detail = getattr(exc, "detail", None)
        if self._contains_model_not_found(detail) or self._contains_model_not_found(str(exc)):
            return (
                "Context Compiler pipe misconfigured: PREPROCESSOR_MODEL_ID is invalid or "
                "not configured in Open WebUI. Configure a valid model id in "
                "Admin Panel → Settings → Models."
            )
        return None

    def _resolve_preprocessor_model_id(self, base_model_id: str | None) -> str | None:
        preprocessor_model_id = _normalize_model_id(self.valves.PREPROCESSOR_MODEL_ID)
        return preprocessor_model_id or base_model_id

    async def _validate_configured_model_ids(
        self,
        request: Request,
        user_payload: dict[str, Any],
        *,
        base_model_id: str | None,
        preprocessor_model_id: str | None,
    ) -> str | None:
        base_model_id = _normalize_model_id(base_model_id)
        preprocessor_model_id = _normalize_model_id(preprocessor_model_id)
        # Best-effort preflight: fail closed only for clear missing-model mismatches.
        # If model discovery fails, preserve runtime behavior and rely on call-path
        # normalization below.
        user = Users.get_user_by_id(user_payload["id"])
        if inspect.isawaitable(user):
            user = await user
        try:
            models = await get_all_models(request, user=user)
        except Exception:
            return None

        known_model_ids: set[str] = set()
        if isinstance(models, list):
            for model in models:
                if not isinstance(model, dict):
                    continue
                model_id = model.get("id")
                if isinstance(model_id, str):
                    known_model_ids.add(model_id)

        if base_model_id and base_model_id not in known_model_ids:
            return (
                "Context Compiler pipe misconfigured: BASE_MODEL_ID was not found "
                "in Open WebUI models."
            )
        if preprocessor_model_id and preprocessor_model_id not in known_model_ids:
            return (
                "Context Compiler pipe misconfigured: PREPROCESSOR_MODEL_ID was not found "
                "in Open WebUI models."
            )
        return None

    async def _llm_fallback_preprocess(
        self,
        message: str,
        state: State,
        *,
        request: Request,
        user_payload: dict[str, Any],
        prompt_profile: str,
        model_id: str | None,
    ) -> tuple[str | None, str | None]:
        model_id = _normalize_model_id(model_id)
        if model_id is None:
            return None, None
        with as_file(_prompt_file_path(prompt_profile)) as prompt_path:
            prompt = render_prompt(prompt_path, state)
        if prompt is None:
            return None, None

        payload: dict[str, Any] = {
            "model": model_id,
            "stream": False,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": message},
            ],
        }
        user = Users.get_user_by_id(user_payload["id"])
        if inspect.isawaitable(user):
            user = await user
        try:
            response = await generate_chat_completion(request, payload, user)
        except Exception as exc:
            normalized_exception = self._normalize_preprocessor_exception(exc)
            if normalized_exception is not None:
                return None, normalized_exception
            return None, None

        normalized_error = self._normalize_preprocessor_error(response)
        if normalized_error is not None:
            return None, normalized_error

        raw_output = _extract_completion_content(response)
        parsed = parse_preprocessor_output(raw_output, source_input=message)
        if parsed is None:
            return None, None
        return parsed, None

    async def _preprocess_user_input(
        self,
        message: str,
        state: State,
        *,
        request: Request,
        user_payload: dict[str, Any],
        prompt_profile: str,
        model_id: str | None,
    ) -> tuple[str | None, str | None]:
        # Heuristic first for precision, determinism, and low latency.
        # If heuristic does not produce a directive, try Open WebUI-native fallback.
        heuristic_result = preprocess_heuristic(message)

        if (
            heuristic_result["outcome"] == PREPROCESS_OUTCOME_DIRECTIVE
            and heuristic_result["directive"]
        ):
            parsed = parse_preprocessor_output(heuristic_result["directive"])
            if parsed is not None:
                return parsed, None

        if _is_directive_shaped_input(message):
            return None, None

        # In debug mode with missing base/preprocessor model ids, skip fallback
        # preprocess entirely so we never attempt an empty-model LLM call.
        model_id = _normalize_model_id(model_id)
        if model_id is None:
            return None, None

        return await self._llm_fallback_preprocess(
            message,
            state,
            request=request,
            user_payload=user_payload,
            prompt_profile=prompt_profile,
            model_id=model_id,
        )

    async def _forward_passthrough(
        self,
        body: dict[str, Any],
        user_payload: dict[str, Any],
        request: Request,
        *,
        base_model_id: str | None,
        state: State | None = None,
    ) -> Any:
        if base_model_id is None:
            if self._allow_missing_base_model_for_debug():
                return (
                    "Context Compiler debug mode: BASE_MODEL_ID is empty; "
                    "skipping model passthrough."
                )
            return (
                "Context Compiler pipe misconfigured: BASE_MODEL_ID is required "
                "(or set ALLOW_MISSING_BASE_MODEL_FOR_DEBUG=true for testing)."
            )
        payload = {**body}
        payload["model"] = base_model_id
        payload["messages"] = _build_forward_messages(body.get("messages"), state=state)
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
        *,
        base_model_id: str | None,
    ) -> Any:
        if base_model_id is None:
            if self._allow_missing_base_model_for_debug():
                return (
                    "Context Compiler debug mode: BASE_MODEL_ID is empty; "
                    "skipping model passthrough."
                )
            return (
                "Context Compiler pipe misconfigured: BASE_MODEL_ID is required "
                "(or set ALLOW_MISSING_BASE_MODEL_FOR_DEBUG=true for testing)."
            )
        payload = {**body}
        payload["model"] = base_model_id

        payload["messages"] = _build_forward_messages(body.get("messages"), state=state)

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
        # Open WebUI integration entrypoint:
        # 1) extract latest user input
        # 2) run preprocess (heuristic -> LLM fallback)
        # 3) pass directive or original input to engine.step(...)
        # 4) map decision back to Open WebUI response behavior
        raw_messages = body.get("messages")
        messages = (
            [msg for msg in raw_messages if isinstance(msg, dict)]
            if isinstance(raw_messages, list)
            else []
        )
        base_model_id = _normalize_model_id(self.valves.BASE_MODEL_ID)
        preprocessor_model_id = _normalize_model_id(self.valves.PREPROCESSOR_MODEL_ID)
        effective_preprocessor_model = preprocessor_model_id or base_model_id
        current_model_id = str(body.get("model", "")).strip()

        if not base_model_id and not self._allow_missing_base_model_for_debug():
            return (
                "Context Compiler pipe misconfigured: BASE_MODEL_ID is required "
                "(or set ALLOW_MISSING_BASE_MODEL_FOR_DEBUG=true for testing)."
            )
        if base_model_id and current_model_id and base_model_id == current_model_id:
            return (
                "Context Compiler pipe misconfigured: BASE_MODEL_ID must not match "
                "the selected pipe model id to avoid recursive routing."
            )
        if (
            effective_preprocessor_model
            and current_model_id
            and effective_preprocessor_model == current_model_id
        ):
            return (
                "Context Compiler pipe misconfigured: PREPROCESSOR_MODEL_ID must not "
                "match the selected pipe model id to avoid recursive routing."
            )

        preflight_error = await self._validate_configured_model_ids(
            __request__,
            __user__,
            base_model_id=base_model_id,
            preprocessor_model_id=effective_preprocessor_model,
        )
        if preflight_error is not None:
            return preflight_error

        latest_user_text = _extract_latest_user_text(messages)
        logger.debug("preprocessor: user_input_found=%s", latest_user_text is not None)

        if latest_user_text is None:
            return await self._forward_passthrough(
                body,
                __user__,
                __request__,
                base_model_id=base_model_id,
            )

        chat_key = _resolve_chat_key(__user__, __chat_id__, __metadata__)
        engine = _ENGINES_BY_CHAT_KEY.get(chat_key)
        if engine is None:
            engine = create_engine()
            checkpoint = _CHECKPOINTS_BY_CHAT_KEY.get(chat_key)
            if checkpoint is not None:
                engine.import_checkpoint_json(checkpoint)
            _ENGINES_BY_CHAT_KEY[chat_key] = engine

        if latest_user_text.strip().lower() == "show state":
            return _render_show_state_summary(engine)

        state_before = engine.state

        preprocessd: str | None = None
        preprocess_error: str | None = None
        if not _has_pending_clarification(engine):
            preprocessd, preprocess_error = await self._preprocess_user_input(
                latest_user_text,
                engine.state,
                request=__request__,
                user_payload=__user__,
                prompt_profile=self.valves.PREPROCESSOR_PROMPT_PROFILE,
                model_id=effective_preprocessor_model,
            )
            if preprocess_error is not None:
                return preprocess_error

        logger.debug("preprocessor: preprocessd=%r", preprocessd)
        # Preserve core behavior: if preprocess yields no directive, use raw user
        # text so the compiler still decides clarify/passthrough/update.
        compile_input = preprocessd if preprocessd is not None else latest_user_text

        logger.debug("preprocessor: engine_input=%r", compile_input)
        decision = engine.step(compile_input)
        if is_clarify(decision):
            kind = DECISION_CLARIFY
        elif is_update(decision):
            kind = DECISION_UPDATE
        else:
            kind = DECISION_PASSTHROUGH
        logger.debug("preprocessor: decision=%s", kind)
        near_miss_prompt = _near_miss_directive_clarify(latest_user_text)
        state_after = get_decision_state(decision)
        if state_after is None:
            state_after = engine.state

        if is_clarify(decision):
            _CHECKPOINTS_BY_CHAT_KEY[chat_key] = engine.export_checkpoint_json()
            return self._with_trace(
                near_miss_prompt or get_clarify_prompt(decision) or "",
                original_input=latest_user_text,
                compiler_input=compile_input,
                decision=decision,
                state_before=state_before,
                state_after=state_after,
                preprocessor_output=preprocessd,
                llm_called=False,
            )
        if near_miss_prompt is not None and is_passthrough(decision):
            return self._with_trace(
                near_miss_prompt,
                original_input=latest_user_text,
                compiler_input=compile_input,
                decision={"kind": DECISION_CLARIFY, "prompt_to_user": near_miss_prompt},
                state_before=state_before,
                state_after=state_after,
                preprocessor_output=preprocessd,
                llm_called=False,
            )
        if is_passthrough(decision):
            compiled_state = _normalize_state(state_after)
            state_injected = "yes" if _has_non_empty_authoritative_state(compiled_state) else "no"
            response = await self._forward_passthrough(
                body,
                __user__,
                __request__,
                base_model_id=base_model_id,
                state=compiled_state,
            )
            return self._with_trace(
                response,
                original_input=latest_user_text,
                compiler_input=compile_input,
                decision=decision,
                state_before=state_before,
                state_after=state_after,
                preprocessor_output=preprocessd,
                llm_called=base_model_id is not None,
                state_injected=state_injected,
            )
        if is_update(decision):
            _CHECKPOINTS_BY_CHAT_KEY[chat_key] = engine.export_checkpoint_json()
            return self._with_trace(
                _summarize_update_from_input(compile_input),
                original_input=latest_user_text,
                compiler_input=compile_input,
                decision=decision,
                state_before=state_before,
                state_after=state_after,
                preprocessor_output=preprocessd,
                llm_called=False,
            )

        compiled_state = _normalize_state(state_after)
        state_injected = "yes" if _has_non_empty_authoritative_state(compiled_state) else "no"
        response = await self._forward_passthrough(
            body,
            __user__,
            __request__,
            base_model_id=base_model_id,
            state=compiled_state,
        )
        return self._with_trace(
            response,
            original_input=latest_user_text,
            compiler_input=compile_input,
            decision=decision,
            state_before=state_before,
            state_after=state_after,
            preprocessor_output=preprocessd,
            llm_called=base_model_id is not None,
            state_injected=state_injected,
        )
