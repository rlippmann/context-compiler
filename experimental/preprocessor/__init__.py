"""Experimental preprocessor integration helpers and prompts."""

from .constants import (
    PRECOMPILE_OUTCOME_DIRECTIVE,
    PRECOMPILE_OUTCOME_NO_DIRECTIVE,
    PRECOMPILE_OUTCOME_UNKNOWN,
    PRECOMPILER_NO_DIRECTIVE_SENTINEL,
    PrecompileOutcome,
)
from .heuristic_preprocessor import PrecompileResult, precompile_heuristic
from .output_validation import (
    parse_precompiler_output,
    parse_preprocessor_output,
    validate_precompiler_output,
)
from .prompt_utils import render_prompt

__all__ = [
    "PRECOMPILE_OUTCOME_DIRECTIVE",
    "PRECOMPILE_OUTCOME_NO_DIRECTIVE",
    "PRECOMPILE_OUTCOME_UNKNOWN",
    "PRECOMPILER_NO_DIRECTIVE_SENTINEL",
    "PrecompileResult",
    "PrecompileOutcome",
    "parse_preprocessor_output",
    "parse_precompiler_output",
    "precompile_heuristic",
    "render_prompt",
    "validate_precompiler_output",
]
