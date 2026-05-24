"""Public observability helpers for host integrations."""

from collections.abc import Mapping
from typing import cast

from .controller import state_diff
from .engine import State

_MAX_INLINE_VALUE_LEN = 180


def _decision_field(decision: object, key: str) -> object:
    if isinstance(decision, Mapping):
        return decision.get(key)
    return getattr(decision, key, None)


def _normalize_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _inline(value: object) -> str:
    rendered = repr(value)
    if len(rendered) <= _MAX_INLINE_VALUE_LEN:
        return rendered
    return f"{rendered[: _MAX_INLINE_VALUE_LEN - 3]}..."


def _summarize_state(state: object) -> str:
    if state is None:
        return "none"
    if isinstance(state, Mapping):
        keys = sorted(str(key) for key in state)
        return f"dict keys={keys}"
    return _inline(state)


def _state_change_summary(before: object, after: object) -> str:
    if before is None and after is None:
        return "none -> none"
    if before == after:
        return "unchanged"
    if isinstance(before, dict) and isinstance(after, dict):
        before_state = cast(State, before)
        after_state = cast(State, after)
        try:
            diff = state_diff(before_state, after_state)
        except Exception:
            diff = None
        if isinstance(diff, Mapping):
            parts: list[str] = []
            premise = diff.get("premise")
            if isinstance(premise, Mapping) and premise.get("changed") is True:
                after_premise = premise.get("after")
                if after_premise is None:
                    parts.append("-premise")
                else:
                    parts.append(f'+premise "{after_premise}"')
            policies = diff.get("policies")
            if isinstance(policies, Mapping):
                added = policies.get("added")
                removed = policies.get("removed")
                changed = policies.get("changed")
                if isinstance(added, Mapping):
                    for item, value in sorted(added.items()):
                        if value == "use":
                            parts.append(f"+use {item}")
                        elif value == "prohibit":
                            parts.append(f"+prohibit {item}")
                if isinstance(removed, Mapping):
                    for item, value in sorted(removed.items()):
                        if value == "use":
                            parts.append(f"-use {item}")
                        elif value == "prohibit":
                            parts.append(f"-prohibit {item}")
                if isinstance(changed, Mapping):
                    for item, transition in sorted(changed.items()):
                        if not isinstance(transition, Mapping):
                            continue
                        after_value = transition.get("after")
                        if after_value == "use":
                            parts.append(f"~use {item}")
                        elif after_value == "prohibit":
                            parts.append(f"~prohibit {item}")
            if parts:
                return ", ".join(parts)

    if isinstance(before, Mapping) and isinstance(after, Mapping):
        before_keys = set(before.keys())
        after_keys = set(after.keys())
        added_keys = sorted(str(key) for key in after_keys - before_keys)
        removed_keys = sorted(str(key) for key in before_keys - after_keys)
        maybe_changed = sorted(
            str(key) for key in before_keys & after_keys if before[key] != after[key]
        )
        key_parts: list[str] = []
        if added_keys:
            key_parts.append(f"added={added_keys}")
        if removed_keys:
            key_parts.append(f"removed={removed_keys}")
        if maybe_changed:
            key_parts.append(f"changed={maybe_changed}")
        if key_parts:
            return "; ".join(key_parts)
    return f"{_summarize_state(before)} -> {_summarize_state(after)}"


def _active_state_summary(state: object) -> str:
    if not isinstance(state, dict):
        return "none"
    try:
        normalized = cast(State, state)
        premise = normalized.get("premise")
        policies = normalized.get("policies")
    except Exception:
        return "none"
    parts: list[str] = []
    if isinstance(premise, str):
        parts.append(f'premise="{premise}"')
    if isinstance(policies, Mapping):
        use_items = sorted(str(item) for item, value in policies.items() if value == "use")
        prohibit_items = sorted(
            str(item) for item, value in policies.items() if value == "prohibit"
        )
        if use_items:
            parts.append("use " + ", ".join(use_items))
        if prohibit_items:
            parts.append("prohibit " + ", ".join(prohibit_items))
    return "; ".join(parts) if parts else "none"


def build_compact_trace_text(
    *,
    decision: object,
    state_before: object,
    state_after: object,
    llm_called: bool,
    state_injected: str,
) -> str:
    """Build OpenWebUI-style compact trace text with stable line formatting."""
    kind = _normalize_text(_decision_field(decision, "kind")) or "unknown"
    lines = ["Context Compiler trace", "", f"decision kind: {kind}"]

    if kind == "update":
        lines.append(f"state change: {_state_change_summary(state_before, state_after)}")
        lines.append(f"active state: {_active_state_summary(state_after)}")
        lines.append(f"downstream LLM call: {'yes' if llm_called else 'no'}")
        lines.append("")
        lines.append(f"state injected: {state_injected}")
        return "\n".join(lines)

    if kind == "clarify":
        prompt = _normalize_text(_decision_field(decision, "prompt_to_user")) or ""
        lines.append(f"clarification prompt: {prompt}")
        lines.append(f"active state: {_active_state_summary(state_after)}")
        lines.append(f"downstream LLM call: {'yes' if llm_called else 'no'}")
        lines.append("state injected: no")
        return "\n".join(lines)

    lines.append(f"active state: {_active_state_summary(state_after)}")
    lines.append(f"downstream LLM call: {'yes' if llm_called else 'no'}")
    lines.append("state injected: no")
    return "\n".join(lines)


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
    """Build a concise human-readable trace line set for host integrations."""
    kind = _normalize_text(_decision_field(decision, "kind")) or "unknown"
    clarify_prompt = _normalize_text(_decision_field(decision, "prompt_to_user"))
    normalized_preproc = _normalize_text(preprocessor_output)

    lines = [
        "Context Compiler trace",
        f"- original input: {original_input}",
        f"- compiler input: {compiler_input}",
    ]
    if normalized_preproc is not None:
        lines.append(f"- preprocessor output: {normalized_preproc}")
    lines.append(f"- decision kind: {kind}")
    if clarify_prompt is not None:
        lines.append(f"- clarification prompt: {clarify_prompt}")
    lines.append(f"- state change: {_state_change_summary(state_before, state_after)}")
    lines.append(f"- downstream LLM call: {'yes' if llm_called else 'no'}")
    return "\n".join(lines)


__all__ = ["build_compact_trace_text", "build_trace"]
