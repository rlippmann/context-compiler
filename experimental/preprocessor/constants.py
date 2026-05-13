"""Shared protocol constants for experimental preprocessor paths."""

import re
from typing import Final, Literal

PREPROCESSOR_NO_DIRECTIVE_SENTINEL: Final = "<NO_DIRECTIVE>"

PREPROCESS_OUTCOME_DIRECTIVE: Final = "directive"
PREPROCESS_OUTCOME_NO_DIRECTIVE: Final = "no_directive"
PREPROCESS_OUTCOME_UNKNOWN: Final = "unknown"
PreprocessOutcome = Literal["directive", "no_directive", "unknown"]

PROMPT_TOKEN_NULL_OR_VALUE: Final = "<NULL_OR_VALUE>"
PROMPT_TOKEN_POLICY_SET: Final = "<SET OF CURRENT POLICY ITEMS>"

CANONICAL_DIRECTIVE_PATTERN_TEXTS: Final[tuple[str, ...]] = (
    r"^set premise (?!to\b)\S(?:.*\S)?$",
    r"^change premise to \S(?:.*\S)?$",
    r"^use \S(?:.*\S)? instead of \S(?:.*\S)?$",
    r"^use (?!.*\sinstead of(?:\s|$))\S(?:.*\S)?$",
    r"^prohibit \S(?:.*\S)?$",
    r"^remove policy \S(?:.*\S)?$",
)
CANONICAL_DIRECTIVE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(pattern) for pattern in CANONICAL_DIRECTIVE_PATTERN_TEXTS
)
CANONICAL_DIRECTIVE_EXACT: Final[frozenset[str]] = frozenset(
    {"clear premise", "reset policies", "clear state"}
)
