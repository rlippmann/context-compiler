"""Shared human-readable integration trace helpers."""

from collections.abc import Mapping

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
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        before_keys = set(before.keys())
        after_keys = set(after.keys())
        added = sorted(str(key) for key in after_keys - before_keys)
        removed = sorted(str(key) for key in before_keys - after_keys)
        maybe_changed = sorted(
            str(key) for key in before_keys & after_keys if before[key] != after[key]
        )
        parts: list[str] = []
        if added:
            parts.append(f"added={added}")
        if removed:
            parts.append(f"removed={removed}")
        if maybe_changed:
            parts.append(f"changed={maybe_changed}")
        if parts:
            return "; ".join(parts)
    return f"{_summarize_state(before)} -> {_summarize_state(after)}"


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
