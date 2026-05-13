"""Experimental preprocessor integration helpers and prompts."""

from .constants import (
    PREPROCESS_OUTCOME_DIRECTIVE,
    PREPROCESS_OUTCOME_NO_DIRECTIVE,
    PREPROCESS_OUTCOME_UNKNOWN,
    PREPROCESSOR_NO_DIRECTIVE_SENTINEL,
    PreprocessOutcome,
)
from .heuristic_preprocessor import PreprocessResult, preprocess_heuristic
from .output_validation import (
    parse_preprocessor_output,
    validate_preprocessor_output,
)
from .prompt_utils import render_prompt

__all__ = [
    "PREPROCESS_OUTCOME_DIRECTIVE",
    "PREPROCESS_OUTCOME_NO_DIRECTIVE",
    "PREPROCESS_OUTCOME_UNKNOWN",
    "PREPROCESSOR_NO_DIRECTIVE_SENTINEL",
    "PreprocessResult",
    "PreprocessOutcome",
    "parse_preprocessor_output",
    "preprocess_heuristic",
    "render_prompt",
    "validate_preprocessor_output",
]
