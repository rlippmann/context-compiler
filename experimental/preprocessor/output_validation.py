"""Shared preprocessor output normalization and validation helpers.

Public API:
- parse_preprocessor_output
- validate_preprocessor_output

Internal helpers are implementation details and may change.
"""

import json
import re
from typing import TypedDict

from .constants import (
    CANONICAL_DIRECTIVE_EXACT,
    CANONICAL_DIRECTIVE_PATTERNS,
    PREPROCESSOR_NO_DIRECTIVE_SENTINEL,
    PreprocessOutcome,
)

__all__ = [
    "parse_preprocessor_output",
    "validate_preprocessor_output",
]


class PreprocessorValidationResult(TypedDict):
    classification: PreprocessOutcome
    output: str | None


_MULTI_CANDIDATE_DIRECTIVE_PATTERN = re.compile(
    r"(?:\band\b|\bthen\b|;|,)\s*(?:set premise\b|change premise\b|use\b|"
    r"prohibit\b|remove policy\b|clear premise\b|reset policies\b|clear state\b)"
)
_SET_PREMISE_TO_NEAR_MISS_PATTERN = re.compile(r"^set premise to\s+(.+\S)\s*$")
_CHANGE_PREMISE_MISSING_TO_NEAR_MISS_PATTERN = re.compile(r"^change premise\s+(?!to\b)(.+\S)\s*$")


def _unknown() -> PreprocessorValidationResult:
    return {"classification": "unknown", "output": None}


def _directive(output: str) -> PreprocessorValidationResult:
    return {"classification": "directive", "output": output}


def _no_directive() -> PreprocessorValidationResult:
    return {"classification": "no_directive", "output": None}


def _is_allowed_directive(text: str) -> bool:
    if text in CANONICAL_DIRECTIVE_EXACT:
        return True
    return any(pattern.fullmatch(text) for pattern in CANONICAL_DIRECTIVE_PATTERNS)


def _contains_multiple_candidate_directives(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return bool(_MULTI_CANDIDATE_DIRECTIVE_PATTERN.search(normalized))


def _is_safe_fallback_directive_rewrite(source_input: str, directive_output: str) -> bool:
    """Reject fallback rewrites that bypass engine-owned premise clarify behavior."""
    source = re.sub(r"\s+", " ", source_input.strip().lower())
    directive = re.sub(r"\s+", " ", directive_output.strip().lower())

    set_premise_to_match = _SET_PREMISE_TO_NEAR_MISS_PATTERN.fullmatch(source)
    if set_premise_to_match is not None:
        payload = set_premise_to_match.group(1).strip()
        if directive == f"set premise {payload}":
            return False

    change_premise_missing_to_match = _CHANGE_PREMISE_MISSING_TO_NEAR_MISS_PATTERN.fullmatch(source)
    if change_premise_missing_to_match is not None:
        payload = change_premise_missing_to_match.group(1).strip()
        if directive == f"change premise to {payload}":
            return False

    return True


def _validate_structured_output(raw_output: object) -> PreprocessorValidationResult:
    if not isinstance(raw_output, dict):
        return _unknown()

    if set(raw_output.keys()) != {"classification", "output"}:
        return _unknown()

    classification = raw_output.get("classification")
    output = raw_output.get("output")
    if not isinstance(classification, str):
        return _unknown()

    if classification == "directive":
        if not isinstance(output, str):
            return _unknown()
        normalized_output = output.strip()
        if not normalized_output:
            return _unknown()
        if _contains_multiple_candidate_directives(normalized_output):
            return _unknown()
        if not _is_allowed_directive(normalized_output):
            return _unknown()
        return _directive(normalized_output)

    if classification == "no_directive":
        if output is not None:
            return _unknown()
        return _no_directive()

    if classification == "unknown":
        if output is not None:
            return _unknown()
        return _unknown()

    return _unknown()


def _validate_text_output(raw_output: str) -> PreprocessorValidationResult:
    stripped = raw_output.strip()
    if not stripped:
        return _unknown()

    if stripped.upper() == PREPROCESSOR_NO_DIRECTIVE_SENTINEL:
        return _no_directive()

    if _contains_multiple_candidate_directives(stripped):
        return _unknown()

    if _is_allowed_directive(stripped):
        return _directive(stripped)

    if stripped[0] in {"{", "["}:
        try:
            parsed_json = json.loads(stripped)
        except json.JSONDecodeError:
            return _unknown()
        return _validate_structured_output(parsed_json)

    return _unknown()


def validate_preprocessor_output(
    raw_output: object, *, source_input: str | None = None
) -> PreprocessorValidationResult:
    """Validate raw preprocessor output into a strict classification/output result.

    Contract:
        - directive: output is a canonical directive string
        - no_directive: output is None
        - unknown: output is None
    """
    if isinstance(raw_output, str):
        validated = _validate_text_output(raw_output)
    else:
        validated = _validate_structured_output(raw_output)

    if (
        source_input is not None
        and validated["classification"] == "directive"
        and isinstance(validated["output"], str)
        and not _is_safe_fallback_directive_rewrite(source_input, validated["output"])
    ):
        return _unknown()

    return validated


def parse_preprocessor_output(raw_output: object, *, source_input: str | None = None) -> str | None:
    """Public validation boundary returning only validated directive output."""
    validated = validate_preprocessor_output(raw_output, source_input=source_input)
    if validated["classification"] == "directive":
        return validated["output"]
    return None
