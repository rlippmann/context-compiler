"""Shared precompiler output normalization and validation helpers.

Public API:
- parse_precompiler_output

Internal helpers are implementation details and may change.
"""

import re

from .constants import (
    CANONICAL_DIRECTIVE_EXACT,
    CANONICAL_DIRECTIVE_PATTERNS,
    PRECOMPILER_NO_DIRECTIVE_SENTINEL,
)

__all__ = ["parse_precompiler_output"]

_MALFORMED_SENTINEL_TAGS = {
    "<NO_DIRECTIPLE>",
    "<NO_DIRECTITIVE>",
    "<NO_DIRECT_DIRECTIVE>",
}
_MALFORMED_SENTINEL_TAG_PATTERN = re.compile(r"^<NO_DIRECTDIRECTIVE[A-Z_]*>$", re.IGNORECASE)


def _normalize_abstain_tag(tag: str) -> str | None:
    upper_tag = tag.strip().upper()
    if upper_tag == PRECOMPILER_NO_DIRECTIVE_SENTINEL:
        return PRECOMPILER_NO_DIRECTIVE_SENTINEL
    if upper_tag in _MALFORMED_SENTINEL_TAGS:
        return PRECOMPILER_NO_DIRECTIVE_SENTINEL
    if _MALFORMED_SENTINEL_TAG_PATTERN.fullmatch(upper_tag):
        return PRECOMPILER_NO_DIRECTIVE_SENTINEL
    return None


def _extract_leading_tag(text: str) -> str | None:
    if not text.startswith("<"):
        return None
    close = text.find(">")
    if close <= 0:
        return None
    return text[: close + 1]


def _normalize_precompiler_output(raw_output: object) -> str | None:
    if not isinstance(raw_output, str):
        return None

    stripped = raw_output.strip()
    if not stripped:
        return stripped

    normalized = _normalize_abstain_tag(stripped)
    if normalized is not None:
        return normalized

    leading_tag = _extract_leading_tag(stripped)
    if leading_tag is not None:
        normalized = _normalize_abstain_tag(leading_tag)
        if normalized is not None:
            return normalized

    non_empty_lines = [line.strip() for line in raw_output.splitlines() if line.strip()]
    if non_empty_lines:
        last_line = non_empty_lines[-1]
        normalized = _normalize_abstain_tag(last_line)
        if normalized is not None:
            return normalized

    return stripped


def _is_allowed_directive(text: str) -> bool:
    if text in CANONICAL_DIRECTIVE_EXACT:
        return True
    return any(pattern.fullmatch(text) for pattern in CANONICAL_DIRECTIVE_PATTERNS)


def parse_precompiler_output(raw_output: object) -> str | None:
    normalized = _normalize_precompiler_output(raw_output)
    if normalized is None:
        return None
    if normalized == PRECOMPILER_NO_DIRECTIVE_SENTINEL:
        return normalized
    if _is_allowed_directive(normalized):
        return normalized
    return None
