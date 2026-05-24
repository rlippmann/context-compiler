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
_DIRECTIVE_CUE_PATTERN = re.compile(
    r"\b(set premise|change premise|use|prohibit|remove policy|clear premise|"
    r"reset policies|clear state)\b"
)
_META_PREFIX_PATTERN = re.compile(
    r"^\s*(?:example:|for example\b|the command is\b|(?:i|he|she|they|docs?|documentation)\s+"
    r"(?:say|says|said)\b)"
)
_MULTI_SEGMENT_PATTERN = re.compile(
    r"^\s*(?:use|prohibit|remove policy|set premise|change premise to|clear premise|"
    r"reset policies|clear state)\b"
    r".*\b(?:because|then continue|and)\b"
)
_SENTENCE_ADJACENT_DIRECTIVE_PATTERN = re.compile(
    r"^[^!?]*\.\s*(?:set premise|change premise|use|prohibit|remove policy|clear premise|"
    r"reset policies|clear state)\b"
)
_PUNCTUATION_TRIM_PATTERN = re.compile(r"[.!]+\s*$")
_REPORTED_SPEECH_QUOTE_PATTERN = re.compile(r"\b(?:say|says|said|docs?|documentation)\b")
_WRAPPER_PAIRS = {
    ("(", ")"),
    ("[", "]"),
}


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
    """Reject fallback rewrites that bypass strict whole-message boundaries."""
    source = re.sub(r"\s+", " ", source_input.strip().lower())
    directive = re.sub(r"\s+", " ", directive_output.strip().lower())

    if _source_input_is_structured_contract_directive(source_input, directive_output):
        return True

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

    if _is_boundary_unsafe_source_input(source_input):
        return False

    normalized_source = _normalize_source_candidate(source_input)
    if not _is_allowed_directive(normalized_source):
        return False

    return directive == normalized_source


def _strip_terminal_punctuation(message: str) -> str:
    return _PUNCTUATION_TRIM_PATTERN.sub("", message).strip()


def _strip_exact_wrapper(message: str) -> str:
    stripped = message.strip()
    if len(stripped) < 2:
        return stripped
    opener = stripped[0]
    closer = stripped[-1]
    if (opener, closer) not in _WRAPPER_PAIRS:
        return stripped
    inner = stripped[1:-1].strip()
    if not inner:
        return stripped
    return inner


def _normalize_source_candidate(source_input: str) -> str:
    stripped = source_input.strip()
    no_punct = _strip_terminal_punctuation(stripped)
    unwrapped = _strip_exact_wrapper(no_punct)
    return re.sub(r"\s+", " ", unwrapped).strip().lower()


def _is_boundary_unsafe_source_input(source_input: str) -> bool:
    lower = source_input.lower()
    normalized = re.sub(r"\s+", " ", source_input.strip().lower())

    if "\n" in source_input or "\r" in source_input:
        return True

    if "```" in source_input or "~~~" in source_input:
        return True

    if "`" in source_input and _DIRECTIVE_CUE_PATTERN.search(normalized):
        return True

    if _META_PREFIX_PATTERN.match(normalized):
        return True

    if "?" in source_input and _DIRECTIVE_CUE_PATTERN.search(normalized):
        return True

    if _MULTI_SEGMENT_PATTERN.match(normalized):
        return True

    if _MULTI_CANDIDATE_DIRECTIVE_PATTERN.search(normalized):
        return True

    if _SENTENCE_ADJACENT_DIRECTIVE_PATTERN.match(normalized):
        return True

    if '"' in source_input and _REPORTED_SPEECH_QUOTE_PATTERN.search(lower):
        return True

    return bool(
        _DIRECTIVE_CUE_PATTERN.search(normalized)
        and not _is_allowed_directive(_normalize_source_candidate(source_input))
    )


def _source_input_is_structured_contract_directive(
    source_input: str, directive_output: str
) -> bool:
    stripped = source_input.strip()
    if not stripped or stripped[0] not in {"{", "["}:
        return False

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return False

    if not isinstance(parsed, dict):
        return False

    if set(parsed.keys()) != {"classification", "output"}:
        return False

    classification = parsed.get("classification")
    output = parsed.get("output")
    return (
        classification == "directive"
        and isinstance(output, str)
        and output.strip().lower() == directive_output.strip().lower()
    )


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
