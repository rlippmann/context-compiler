"""Shared precompiler output normalization and validation helpers.

Public API:
- validate_precompiler_output
- parse_precompiler_output

Internal helpers are implementation details and may change.
"""

import json
import re
from typing import TypedDict

from .constants import (
    CANONICAL_DIRECTIVE_EXACT,
    CANONICAL_DIRECTIVE_PATTERNS,
    PRECOMPILER_NO_DIRECTIVE_SENTINEL,
    PrecompileOutcome,
)

__all__ = ["parse_precompiler_output", "validate_precompiler_output"]


class PrecompilerValidationResult(TypedDict):
    classification: PrecompileOutcome
    output: str | None


_MULTI_CANDIDATE_DIRECTIVE_PATTERN = re.compile(
    r"(?:\band\b|\bthen\b|;|,)\s*(?:set premise\b|change premise\b|use\b|"
    r"prohibit\b|remove policy\b|clear premise\b|reset policies\b|clear state\b)"
)


def _unknown() -> PrecompilerValidationResult:
    return {"classification": "unknown", "output": None}


def _directive(output: str) -> PrecompilerValidationResult:
    return {"classification": "directive", "output": output}


def _no_directive() -> PrecompilerValidationResult:
    return {"classification": "no_directive", "output": None}


def _is_allowed_directive(text: str) -> bool:
    if text in CANONICAL_DIRECTIVE_EXACT:
        return True
    return any(pattern.fullmatch(text) for pattern in CANONICAL_DIRECTIVE_PATTERNS)


def _contains_multiple_candidate_directives(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return bool(_MULTI_CANDIDATE_DIRECTIVE_PATTERN.search(normalized))


def _validate_structured_output(raw_output: object) -> PrecompilerValidationResult:
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


def _validate_text_output(raw_output: str) -> PrecompilerValidationResult:
    stripped = raw_output.strip()
    if not stripped:
        return _unknown()

    if stripped.upper() == PRECOMPILER_NO_DIRECTIVE_SENTINEL:
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


def validate_precompiler_output(raw_output: object) -> PrecompilerValidationResult:
    """Validate raw precompiler output into a strict classification/output result.

    Contract:
        - directive: output is a canonical directive string
        - no_directive: output is None
        - unknown: output is None
    """
    if isinstance(raw_output, str):
        return _validate_text_output(raw_output)
    return _validate_structured_output(raw_output)


def parse_precompiler_output(raw_output: object) -> str | None:
    """Compatibility wrapper returning only validated directive output.

    Args:
        raw_output: Raw value produced by heuristic or LLM preprocessing.

    Returns:
        Canonical directive string when valid, else None.

    Notes:
        This is the public validation boundary. Preprocessor outputs must be
        passed through this function before being applied to compiler paths.
    """
    validated = validate_precompiler_output(raw_output)
    if validated["classification"] == "directive":
        return validated["output"]
    return None
