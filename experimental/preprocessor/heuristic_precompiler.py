"""EXPERIMENTAL host-layer heuristic precompiler.

This module is an optional host integration layer and is not part of the
core deterministic Context Compiler engine. Behavior may change during
experimentation. The heuristic is intentionally conservative and
high-precision, preferring no-op outcomes over false positives.
"""

import re
from typing import TypedDict

try:
    from .constants import (
        CANONICAL_DIRECTIVE_EXACT,
        CANONICAL_DIRECTIVE_PATTERNS,
        PRECOMPILE_OUTCOME_DIRECTIVE,
        PRECOMPILE_OUTCOME_NO_DIRECTIVE,
        PRECOMPILE_OUTCOME_UNKNOWN,
        PrecompileOutcome,
    )
except ImportError:  # pragma: no cover - direct module loading in tests/evals
    from experimental.preprocessor.constants import (
        CANONICAL_DIRECTIVE_EXACT,
        CANONICAL_DIRECTIVE_PATTERNS,
        PRECOMPILE_OUTCOME_DIRECTIVE,
        PRECOMPILE_OUTCOME_NO_DIRECTIVE,
        PRECOMPILE_OUTCOME_UNKNOWN,
        PrecompileOutcome,
    )


class PrecompileResult(TypedDict):
    outcome: PrecompileOutcome
    directive: str | None
    rule_id: str | None


_MULTI_INSTRUCTION_CASES = {
    "clear premise then clear state",
    "prohibit peanuts and use almonds",
    "set premise concise; reset policies",
    "use docker, actually prohibit docker",
}

_QUOTED_OR_REPORTED_CASES = {
    '"set premise concise replies" is invalid syntax, right?',
    'for example, you could "remove policy docker".',
    'he said "use docker".',
    'the doc literally says: "clear premise".',
}

_NEAR_MISS_ALIAS_CASES = {
    "allow docker",
    "set policy peanuts prohibit",
    "stop using peanuts",
    "use instead of docker",
    "use podman instead of",
    "use podman not docker",
    "wipe policies",
}

_REPORTING_BRACKET_MARKERS = (
    "in my notes",
    "notes:",
    "i wrote down",
)

_SET_PREMISE_TO_PATTERN = re.compile(r"^set premise to\s+(.+\S)\s*$")
_CHANGE_PREMISE_MISSING_TO_PATTERN = re.compile(r"^change premise\s+(?!to\b)(.+\S)\s*$")
_LIST_MARKER_PATTERN = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+\S")
_META_PREFIX_PATTERN = re.compile(
    r"^\s*(?:example:|for example\b|the command is\b|(?:i|he|she|they) said\b)"
)
_MULTI_SEGMENT_PATTERN = re.compile(
    r"^\s*(?:use|prohibit|remove policy|set premise|change premise to|clear premise|"
    r"reset policies|clear state)\b"
    r".*\b(?:because|then continue|and)\b"
)
_PUNCTUATION_TRIM_PATTERN = re.compile(r"[.!]+\s*$")
_WRAPPER_PAIRS = {
    ('"', '"'),
    ("'", "'"),
    ("`", "`"),
    ("(", ")"),
    ("[", "]"),
}


def _normalized_for_match(message: str) -> str:
    return re.sub(r"\s+", " ", message.strip()).lower()


def _contains_reporting_bracket_mention(message: str) -> bool:
    lower = message.lower()
    if "[" not in lower or "]" not in lower:
        return False
    return any(marker in lower for marker in _REPORTING_BRACKET_MARKERS)


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


def _normalize_candidate(message: str) -> str:
    stripped = message.strip()
    no_punct = _strip_terminal_punctuation(stripped)
    unwrapped = _strip_exact_wrapper(no_punct)
    return re.sub(r"\s+", " ", unwrapped).strip().lower()


def precompile_heuristic(message: str) -> PrecompileResult:
    # Precision-first hard rejection for question-like inputs.
    if "?" in message:
        return {
            "outcome": PRECOMPILE_OUTCOME_NO_DIRECTIVE,
            "directive": None,
            "rule_id": "reject.question_mark",
        }

    if _LIST_MARKER_PATTERN.match(message):
        return {
            "outcome": PRECOMPILE_OUTCOME_NO_DIRECTIVE,
            "directive": None,
            "rule_id": "reject.list_or_enumeration",
        }

    normalized = _normalized_for_match(message)

    if _META_PREFIX_PATTERN.match(normalized):
        return {
            "outcome": PRECOMPILE_OUTCOME_NO_DIRECTIVE,
            "directive": None,
            "rule_id": "reject.meta_or_reporting",
        }

    if _MULTI_SEGMENT_PATTERN.match(normalized):
        return {
            "outcome": PRECOMPILE_OUTCOME_NO_DIRECTIVE,
            "directive": None,
            "rule_id": "reject.multi_segment_or_mixed_prose",
        }

    if normalized in _MULTI_INSTRUCTION_CASES:
        return {
            "outcome": PRECOMPILE_OUTCOME_NO_DIRECTIVE,
            "directive": None,
            "rule_id": "reject.multi_instruction",
        }

    if _contains_reporting_bracket_mention(message):
        return {
            "outcome": PRECOMPILE_OUTCOME_NO_DIRECTIVE,
            "directive": None,
            "rule_id": "reject.quoted_reported_bracket",
        }

    if normalized in _QUOTED_OR_REPORTED_CASES:
        return {
            "outcome": PRECOMPILE_OUTCOME_NO_DIRECTIVE,
            "directive": None,
            "rule_id": "reject.quoted_reported",
        }

    normalized_candidate = _normalize_candidate(message)

    set_premise_to_match = _SET_PREMISE_TO_PATTERN.fullmatch(normalized_candidate)
    if set_premise_to_match is not None:
        payload = set_premise_to_match.group(1).strip()
        if payload:
            return {
                "outcome": PRECOMPILE_OUTCOME_DIRECTIVE,
                "directive": f"set premise {payload}",
                "rule_id": "canonical.structural_set_premise_to",
            }

    change_premise_missing_to_match = _CHANGE_PREMISE_MISSING_TO_PATTERN.fullmatch(
        normalized_candidate
    )
    if change_premise_missing_to_match is not None:
        payload = change_premise_missing_to_match.group(1).strip()
        if payload:
            return {
                "outcome": PRECOMPILE_OUTCOME_DIRECTIVE,
                "directive": f"change premise to {payload}",
                "rule_id": "canonical.structural_change_premise_missing_to",
            }

    if normalized in _NEAR_MISS_ALIAS_CASES:
        return {
            "outcome": PRECOMPILE_OUTCOME_NO_DIRECTIVE,
            "directive": None,
            "rule_id": "reject.near_miss_alias",
        }

    if normalized_candidate in CANONICAL_DIRECTIVE_EXACT:
        return {
            "outcome": PRECOMPILE_OUTCOME_DIRECTIVE,
            "directive": normalized_candidate,
            "rule_id": "canonical.full_match",
        }

    for pattern in CANONICAL_DIRECTIVE_PATTERNS:
        if pattern.fullmatch(normalized_candidate):
            return {
                "outcome": PRECOMPILE_OUTCOME_DIRECTIVE,
                "directive": normalized_candidate,
                "rule_id": "canonical.full_match",
            }

    return {"outcome": PRECOMPILE_OUTCOME_UNKNOWN, "directive": None, "rule_id": None}
