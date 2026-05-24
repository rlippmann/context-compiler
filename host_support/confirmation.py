"""Host-support confirmation helpers aligned with directive grammar behavior.

This module provides host-side logic for confirmation token handling. It mirrors
the confirmation normalization and token behavior defined in
`DirectiveGrammarSpec.md` and must stay aligned with that specification to avoid
drift between engine and host behavior.
"""

import re

_TRAILING_CONFIRM_PUNCT_RE = re.compile(r"[.,!?]+$")

_AFFIRMATIVE_CONFIRMATION_TOKENS = frozenset(
    {"yes", "yes please", "yep", "yeah", "sure", "ok", "okay"}
)
_NEGATIVE_CONFIRMATION_TOKENS = frozenset({"no", "nope", "no thanks"})

CONFIRMATION_TOKENS: frozenset[str] = (
    _AFFIRMATIVE_CONFIRMATION_TOKENS | _NEGATIVE_CONFIRMATION_TOKENS
)


def _render_item_label(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalize_confirmation_text(value: str) -> str:
    """Normalize confirmation text using directive grammar confirmation rules."""
    normalized = value.strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = _TRAILING_CONFIRM_PUNCT_RE.sub("", normalized).strip()
    return re.sub(r"\s+", " ", normalized)


def is_confirmation_text(value: str) -> bool:
    """Return whether input is a recognized confirmation token."""
    return _normalize_confirmation_text(value) in CONFIRMATION_TOKENS


def _summarize_pending_confirmation_update(pending: object) -> str:
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


def summarize_confirmation_update(user_input: str, pending: object) -> str:
    """Return deterministic host summary text for confirmation-only updates.

    This helper is intentionally conservative:
    - negative confirmations always return ``State unchanged.``
    - affirmative confirmations return an exact deterministic summary only when
      pending metadata unambiguously identifies the confirmed transition
    - otherwise it falls back to ``State updated.``
    """
    normalized = _normalize_confirmation_text(user_input)
    if normalized in _NEGATIVE_CONFIRMATION_TOKENS:
        return "State unchanged."
    if normalized not in _AFFIRMATIVE_CONFIRMATION_TOKENS:
        return "State updated."
    return _summarize_pending_confirmation_update(pending)


def summarize_confirmation_update_from_engine(user_input: str, engine: object) -> str:
    """Return confirmation summary using pending details from an engine checkpoint."""
    checkpoint: object = None
    export_checkpoint = getattr(engine, "export_checkpoint", None)
    if callable(export_checkpoint):
        try:
            checkpoint = export_checkpoint()
        except Exception:
            checkpoint = None
    pending = checkpoint.get("pending") if isinstance(checkpoint, dict) else None
    return summarize_confirmation_update(user_input, pending)


def summarize_confirmation_update_from_checkpoint(user_input: str, checkpoint: object) -> str:
    """Return confirmation summary using pending details from a checkpoint object."""
    pending = checkpoint.get("pending") if isinstance(checkpoint, dict) else None
    return summarize_confirmation_update(user_input, pending)
