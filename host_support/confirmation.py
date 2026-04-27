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


def normalize_confirmation_text(value: str) -> str:
    """Normalize confirmation text using directive grammar confirmation rules."""
    normalized = value.strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = _TRAILING_CONFIRM_PUNCT_RE.sub("", normalized).strip()
    return re.sub(r"\s+", " ", normalized)


def is_confirmation_text(value: str) -> bool:
    """Return whether input is a recognized confirmation token."""
    return normalize_confirmation_text(value) in CONFIRMATION_TOKENS
