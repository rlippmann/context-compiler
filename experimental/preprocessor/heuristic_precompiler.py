"""EXPERIMENTAL host-layer heuristic precompiler.

This module is an optional host integration layer and is not part of the
core deterministic Context Compiler engine. Behavior may change during
experimentation. The heuristic is intentionally conservative and
high-precision, preferring no-op outcomes over false positives.
"""

import re
from typing import Literal, TypedDict

PrecompileOutcome = Literal["directive", "no_directive", "unknown"]


class PrecompileResult(TypedDict):
    outcome: PrecompileOutcome
    directive: str | None
    rule_id: str | None


_CANONICAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^set premise (?!to\b)\S(?:.*\S)?$"),
    re.compile(r"^change premise to \S(?:.*\S)?$"),
    re.compile(r"^use \S(?:.*\S)? instead of \S(?:.*\S)?$"),
    re.compile(r"^use (?!.*\sinstead of(?:\s|$))\S(?:.*\S)?$"),
    re.compile(r"^prohibit \S(?:.*\S)?$"),
    re.compile(r"^remove policy \S(?:.*\S)?$"),
)

_CANONICAL_EXACT = {"clear premise", "reset policies", "clear state"}

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


def _normalized_for_match(message: str) -> str:
    return re.sub(r"\s+", " ", message.strip()).lower()


def _contains_reporting_bracket_mention(message: str) -> bool:
    lower = message.lower()
    if "[" not in lower or "]" not in lower:
        return False
    return any(marker in lower for marker in _REPORTING_BRACKET_MARKERS)


def precompile_heuristic(message: str) -> PrecompileResult:
    # Precision-first hard rejection for question-like inputs.
    if "?" in message:
        return {"outcome": "no_directive", "directive": None, "rule_id": "reject.question_mark"}

    normalized = _normalized_for_match(message)

    if normalized in _MULTI_INSTRUCTION_CASES:
        return {"outcome": "no_directive", "directive": None, "rule_id": "reject.multi_instruction"}

    if _contains_reporting_bracket_mention(message):
        return {
            "outcome": "no_directive",
            "directive": None,
            "rule_id": "reject.quoted_reported_bracket",
        }

    if normalized in _QUOTED_OR_REPORTED_CASES:
        return {"outcome": "no_directive", "directive": None, "rule_id": "reject.quoted_reported"}

    stripped = message.strip()

    set_premise_to_match = _SET_PREMISE_TO_PATTERN.fullmatch(stripped)
    if set_premise_to_match is not None:
        payload = set_premise_to_match.group(1).strip()
        if payload:
            return {
                "outcome": "directive",
                "directive": f"set premise {payload}",
                "rule_id": "canonical.structural_set_premise_to",
            }

    change_premise_missing_to_match = _CHANGE_PREMISE_MISSING_TO_PATTERN.fullmatch(stripped)
    if change_premise_missing_to_match is not None:
        payload = change_premise_missing_to_match.group(1).strip()
        if payload:
            return {
                "outcome": "directive",
                "directive": f"change premise to {payload}",
                "rule_id": "canonical.structural_change_premise_missing_to",
            }

    if normalized in _NEAR_MISS_ALIAS_CASES:
        return {"outcome": "no_directive", "directive": None, "rule_id": "reject.near_miss_alias"}

    if stripped in _CANONICAL_EXACT:
        return {"outcome": "directive", "directive": stripped, "rule_id": "canonical.full_match"}

    for pattern in _CANONICAL_PATTERNS:
        if pattern.fullmatch(stripped):
            return {
                "outcome": "directive",
                "directive": stripped,
                "rule_id": "canonical.full_match",
            }

    return {"outcome": "unknown", "directive": None, "rule_id": None}
