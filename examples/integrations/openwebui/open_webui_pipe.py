"""
title: Context Compiler Pipe
author: rlippmann
author_url: https://github.com/rlippmann/context-compiler
funding_url: https://github.com/rlippmann/context-compiler
version: 0.4
requirements: context-compiler>=0.6.10

Minimal Open WebUI Pipe integration for Context Compiler.

This integration demonstrates mapping Context Compiler `Decision` output into
Open WebUI request flow.

Scope is intentionally limited:
- Single Pipe Function for Open WebUI v0.7.2.
- In-memory per-process engine map keyed by chat key.
- No persistence, no multi-worker coordination, no external storage.
"""

import inspect
import logging
import re
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


import host_support.confirmation as _confirmation
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
_NEGATIVE_CONFIRMATION_TOKENS = {"no", "nope", "no thanks"}
_TRAILING_CONFIRM_PUNCT_RE = re.compile(r"[.,!?]+$")


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


def _normalize_confirmation_for_summary(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = _TRAILING_CONFIRM_PUNCT_RE.sub("", normalized).strip()
    return re.sub(r"\s+", " ", normalized)


def _render_item_label(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _summarize_confirmation_update(user_input: str, pending: object) -> str:
    summarize_fn = getattr(_confirmation, "summarize_confirmation_update", None)
    if callable(summarize_fn):
        return cast(str, summarize_fn(user_input, pending))

    normalized = _normalize_confirmation_for_summary(user_input)
    if normalized in _NEGATIVE_CONFIRMATION_TOKENS:
        return "State unchanged."
    if not isinstance(pending, dict):
        return "State updated."

    replacement = pending.get("replacement")
    if not isinstance(replacement, dict):
        return "State updated."

    kind = replacement.get("kind")
    new_item = replacement.get("new_item")
    old_item = replacement.get("old_item")
    if kind == "use_only" and isinstance(new_item, str):
        new_label = _render_item_label(new_item)
        if new_label:
            return f"State updated: Use {new_label}."
        return "State updated."

    if kind == "replace_use" and isinstance(new_item, str) and isinstance(old_item, str):
        new_label = _render_item_label(new_item)
        old_label = _render_item_label(old_item)
        if not new_label or not old_label:
            return "State updated."
        prompt = pending.get("prompt_to_user")
        prohibited_old_prompt = (
            f'"{old_item}" is currently prohibited. '
            f'Did you mean to remove it and use "{new_item}" instead?'
        )
        if prompt == prohibited_old_prompt:
            return f"State updated: Removed prohibition on {old_label}; use {new_label}."
        return f"State updated: Replaced {old_label} with {new_label}."

    return "State updated."


class Pipe:
    """Map Context Compiler decisions into Open WebUI pipe behavior.

    - ``clarify`` returns plain text and skips model forwarding.
    - ``passthrough`` forwards with minimal mutation.
    - ``update`` injects one compiler-owned system message and forwards.
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

    async def _forward_passthrough(
        self,
        body: dict[str, Any],
        user_payload: dict[str, Any],
        request: Request,
    ) -> Any:
        """Forward with a shallow body copy and model override only."""
        payload = {**body}
        payload["model"] = self.valves.BASE_MODEL_ID
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
            [dict(msg) for msg in raw_messages if isinstance(msg, dict)]
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

        checkpoint_before = engine.export_checkpoint()
        pending_before = checkpoint_before.get("pending")
        logger.debug("pipe: engine_input=%r", latest_user_text)
        decision = engine.step(latest_user_text)
        kind = decision["kind"]
        logger.debug("pipe: decision=%s", kind)

        if kind == "clarify":
            _CHECKPOINTS_BY_CHAT_KEY[chat_key] = engine.export_checkpoint_json()
            return decision["prompt_to_user"] or ""
        if kind == "passthrough":
            return await self._forward_passthrough(body, __user__, __request__)
        if kind == "update":
            _CHECKPOINTS_BY_CHAT_KEY[chat_key] = engine.export_checkpoint_json()
            if _confirmation.is_confirmation_text(latest_user_text) and pending_before is not None:
                return _summarize_confirmation_update(latest_user_text, pending_before)
            return await self._forward_update(body, __user__, __request__, engine.state)

        return await self._forward_passthrough(body, __user__, __request__)
