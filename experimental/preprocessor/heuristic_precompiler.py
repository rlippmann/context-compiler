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
_DIRECTIVE_CUE_PATTERN = re.compile(
    r"\b(set premise|change premise|use|prohibit|remove policy|clear premise|"
    r"reset policies|clear state)\b"
)
_MULTI_CANDIDATE_DIRECTIVE_PATTERN = re.compile(
    r"(?:\band\b|\bthen\b|;|,)\s*(?:set premise\b|change premise\b|use\b|"
    r"prohibit\b|remove policy\b|clear premise\b|reset policies\b|clear state\b)"
)
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
    """Run the conservative structural heuristic precompile pass.

    Args:
        message: Raw user text to evaluate as a possible directive.

    Returns:
        A PrecompileResult with:
        - outcome="directive" and a canonical directive string when matched
        - outcome="no_directive" when the heuristic abstains/rejects
        - outcome="unknown" when unresolved and LLM fallback may be attempted

    Notes:
        This pass is precision-first and intentionally narrow. It may abstain
        on ambiguous or mixed-intent inputs.
    """
    if _LIST_MARKER_PATTERN.match(message):
        return {
            "outcome": PRECOMPILE_OUTCOME_UNKNOWN,
            "directive": None,
            "rule_id": "reject.list_or_enumeration",
        }

    normalized = _normalized_for_match(message)

    if "?" in message and _DIRECTIVE_CUE_PATTERN.search(normalized):
        return {
            "outcome": PRECOMPILE_OUTCOME_UNKNOWN,
            "directive": None,
            "rule_id": "reject.question_form",
        }

    if _META_PREFIX_PATTERN.match(normalized):
        return {
            "outcome": PRECOMPILE_OUTCOME_UNKNOWN,
            "directive": None,
            "rule_id": "reject.meta_or_reporting",
        }

    if _MULTI_SEGMENT_PATTERN.match(normalized):
        return {
            "outcome": PRECOMPILE_OUTCOME_UNKNOWN,
            "directive": None,
            "rule_id": "reject.multi_segment_or_mixed_prose",
        }

    if normalized in _MULTI_INSTRUCTION_CASES:
        return {
            "outcome": PRECOMPILE_OUTCOME_UNKNOWN,
            "directive": None,
            "rule_id": "reject.multi_instruction",
        }

    if _contains_reporting_bracket_mention(message):
        return {
            "outcome": PRECOMPILE_OUTCOME_UNKNOWN,
            "directive": None,
            "rule_id": "reject.quoted_reported_bracket",
        }

    if normalized in _QUOTED_OR_REPORTED_CASES:
        return {
            "outcome": PRECOMPILE_OUTCOME_UNKNOWN,
            "directive": None,
            "rule_id": "reject.quoted_reported",
        }

    normalized_candidate = _normalize_candidate(message)

    if normalized in _NEAR_MISS_ALIAS_CASES:
        return {
            "outcome": PRECOMPILE_OUTCOME_UNKNOWN,
            "directive": None,
            "rule_id": "reject.near_miss_alias",
        }

    if _MULTI_CANDIDATE_DIRECTIVE_PATTERN.search(normalized_candidate):
        return {
            "outcome": PRECOMPILE_OUTCOME_UNKNOWN,
            "directive": None,
            "rule_id": "reject.multi_candidate_directive",
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

    if _DIRECTIVE_CUE_PATTERN.search(normalized_candidate):
        return {
            "outcome": PRECOMPILE_OUTCOME_UNKNOWN,
            "directive": None,
            "rule_id": "reject.directive_adjacent_unsafe",
        }

    return {
        "outcome": PRECOMPILE_OUTCOME_NO_DIRECTIVE,
        "directive": None,
        "rule_id": "reject.confident_non_directive",
    }
