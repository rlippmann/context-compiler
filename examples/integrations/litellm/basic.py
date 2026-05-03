"""Minimal LiteLLM integration with Context Compiler.

Flow:
1. Call engine.step(user_input)
2. clarify -> return prompt_to_user (no model call)
3. update -> return deterministic acknowledgment text (no model call)
4. passthrough -> call LiteLLM with compiled state + user input

Intended host usage:
- collect user input
- call handle_turn(user_input, engine)
- display returned assistant text
"""

import logging
import re
from collections.abc import Callable, Mapping, Sequence
from importlib import import_module
from typing import TypedDict, cast

from context_compiler import State, get_policy_items, get_premise_value
from context_compiler.engine import Engine

try:
    from host_support import is_confirmation_text, summarize_confirmation_update
except ImportError:
    import host_support.confirmation as _confirmation

    is_confirmation_text = _confirmation.is_confirmation_text
    summarize_confirmation_update = _confirmation.summarize_confirmation_update
try:
    from host_support import build_trace
except ImportError:
    try:
        from host_support.observability import build_trace
    except ImportError:

        def build_trace(
            *,
            original_input: str,
            compiler_input: str,
            decision: object,
            state_before: object,
            state_after: object,
            preprocessor_output: str | None = None,
            llm_called: bool = False,
        ) -> str:
            del (
                original_input,
                compiler_input,
                decision,
                state_before,
                state_after,
                preprocessor_output,
                llm_called,
            )
            return ""


try:
    from host_support import print_startup_config, resolve_provider_config
except ImportError:
    from host_support.provider_mode import print_startup_config, resolve_provider_config

logger = logging.getLogger(__name__)
# Example-only in-memory checkpoint store.
# This keeps continuation state only for the current process lifetime.
# Real deployments should persist checkpoints externally (DB/Redis/etc.),
# or restart continuity for pending flows will be lost.
_CHECKPOINTS_BY_SESSION_KEY: dict[str, str] = {}
_RESTORED_ENGINE_BY_SESSION_KEY: dict[str, int] = {}
_NEGATIVE_CONFIRMATION_TOKENS = {"no", "nope", "no thanks"}
_TRAILING_CONFIRM_PUNCT_RE = re.compile(r"[.,!?]+$")
SHOW_CONTEXT_COMPILER_TRACE = False


class _LiteLLMCallKwargs(TypedDict, total=False):
    model: str
    messages: list[dict[str, str]]
    api_key: str
    temperature: float
    api_base: str


def _extract_response_content(response: object) -> str | None:
    if isinstance(response, Mapping):
        choices = response.get("choices")
        if isinstance(choices, Sequence) and choices:
            first = choices[0]
            if isinstance(first, Mapping):
                message = first.get("message")
                if isinstance(message, Mapping):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content

    choices_attr = getattr(response, "choices", None)
    if isinstance(choices_attr, Sequence) and choices_attr:
        first = choices_attr[0]
        message_attr = getattr(first, "message", None)
        content_attr = getattr(message_attr, "content", None)
        if isinstance(content_attr, str):
            return content_attr

    return None


def _render_compiled_state_contract(compiled_state: State) -> str:
    premise = get_premise_value(compiled_state)
    use_items = sorted(get_policy_items(compiled_state, "use"))
    prohibit_items = sorted(get_policy_items(compiled_state, "prohibit"))

    lines: list[str] = ["The following constraints are authoritative."]
    if premise:
        lines.append(f"Current premise: {premise}.")
    if use_items:
        lines.append("Items marked use: " + ", ".join(use_items) + ".")
    if prohibit_items:
        lines.append("Items marked prohibit: " + ", ".join(prohibit_items) + ".")
    lines.append("If user text conflicts with constraints, follow constraints exactly.")

    return "Host policy contract:\n" + "\n".join(f"- {line}" for line in lines)


def _build_messages(user_input: str, compiled_state: State) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": "You are a helpful assistant.\n"
            + _render_compiled_state_contract(compiled_state),
        },
        {"role": "user", "content": user_input},
    ]


def _call_litellm(messages: list[dict[str, str]]) -> str:
    try:
        litellm_module = import_module("litellm")
    except ModuleNotFoundError as exc:
        raise RuntimeError("litellm is required. Install with: pip install litellm") from exc
    completion_fn = cast(Callable[..., object], litellm_module.completion)

    config = resolve_provider_config(default_model="openai/gpt-4o-mini")
    print_startup_config(config, logger=logger)

    kwargs: _LiteLLMCallKwargs = {
        "model": config.model,
        "messages": messages,
        "temperature": 0,
        "api_base": config.base_url,
    }
    if config.api_key:
        kwargs["api_key"] = config.api_key

    response = completion_fn(**kwargs)
    content = _extract_response_content(response)
    if content is None:
        raise RuntimeError("LiteLLM response missing choices[0].message.content")
    return content


def _restore_session_checkpoint_if_needed(engine: Engine, session_key: str | None) -> None:
    if session_key is None:
        return
    engine_id = id(engine)
    if _RESTORED_ENGINE_BY_SESSION_KEY.get(session_key) == engine_id:
        return

    checkpoint = _CHECKPOINTS_BY_SESSION_KEY.get(session_key)
    if checkpoint is not None:
        engine.import_checkpoint_json(checkpoint)
    _RESTORED_ENGINE_BY_SESSION_KEY[session_key] = engine_id


def _persist_session_checkpoint_if_needed(
    engine: Engine, kind: str, session_key: str | None
) -> None:
    if session_key is None:
        return
    if kind not in {"update", "clarify"}:
        return
    _CHECKPOINTS_BY_SESSION_KEY[session_key] = engine.export_checkpoint_json()


def _normalize_confirmation_for_summary(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = _TRAILING_CONFIRM_PUNCT_RE.sub("", normalized).strip()
    return re.sub(r"\s+", " ", normalized)


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


def _summarize_confirmation_update(user_input: str, pending: object) -> str:
    summarize_fn = summarize_confirmation_update
    if callable(summarize_fn):
        return summarize_fn(user_input, pending)

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


def _append_trace(
    response_text: str,
    *,
    original_input: str,
    compiler_input: str,
    decision: object,
    state_before: object,
    state_after: object,
    llm_called: bool,
) -> str:
    if not SHOW_CONTEXT_COMPILER_TRACE:
        return response_text
    trace_text = build_trace(
        original_input=original_input,
        compiler_input=compiler_input,
        decision=decision,
        state_before=state_before,
        state_after=state_after,
        llm_called=llm_called,
    )
    return f"{response_text}\n\n{trace_text}"


def handle_turn(user_input: str, engine: Engine, *, session_key: str | None = None) -> str:
    _restore_session_checkpoint_if_needed(engine, session_key)
    checkpoint_before = engine.export_checkpoint()
    pending_before = checkpoint_before.get("pending")
    logger.debug("litellm_basic: engine_input=%s", f"user_input len={len(user_input)}")
    decision = engine.step(user_input)
    kind = cast(str, decision["kind"])
    logger.debug("litellm_basic: decision=%s", kind)
    near_miss_prompt = _near_miss_directive_clarify(user_input)

    if kind == "clarify":
        _persist_session_checkpoint_if_needed(engine, kind, session_key)
        response_text = near_miss_prompt or decision["prompt_to_user"] or ""
        return _append_trace(
            response_text,
            original_input=user_input,
            compiler_input=user_input,
            decision=decision,
            state_before=checkpoint_before.get("authoritative_state"),
            state_after=engine.state,
            llm_called=False,
        )
    if near_miss_prompt is not None and kind == "passthrough":
        return _append_trace(
            near_miss_prompt,
            original_input=user_input,
            compiler_input=user_input,
            decision={"kind": "clarify", "prompt_to_user": near_miss_prompt},
            state_before=checkpoint_before.get("authoritative_state"),
            state_after=engine.state,
            llm_called=False,
        )
    _persist_session_checkpoint_if_needed(engine, kind, session_key)
    if kind == "update" and is_confirmation_text(user_input) and pending_before is not None:
        response_text = _summarize_confirmation_update(user_input, pending_before)
        return _append_trace(
            response_text,
            original_input=user_input,
            compiler_input=user_input,
            decision=decision,
            state_before=checkpoint_before.get("authoritative_state"),
            state_after=engine.state,
            llm_called=False,
        )
    if kind == "update":
        response_text = _summarize_update_from_input(user_input)
        return _append_trace(
            response_text,
            original_input=user_input,
            compiler_input=user_input,
            decision=decision,
            state_before=checkpoint_before.get("authoritative_state"),
            state_after=engine.state,
            llm_called=False,
        )

    compiled_state = decision["state"] if decision["state"] is not None else engine.state
    messages = _build_messages(user_input, compiled_state)
    response_text = _call_litellm(messages)
    return _append_trace(
        response_text,
        original_input=user_input,
        compiler_input=user_input,
        decision=decision,
        state_before=checkpoint_before.get("authoritative_state"),
        state_after=compiled_state,
        llm_called=True,
    )
