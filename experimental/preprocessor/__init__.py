"""Experimental preprocessor integration helpers and prompts."""

from .constants import (
    PRECOMPILE_OUTCOME_DIRECTIVE,
    PRECOMPILE_OUTCOME_NO_DIRECTIVE,
    PRECOMPILE_OUTCOME_UNKNOWN,
    PRECOMPILER_NO_DIRECTIVE_SENTINEL,
    PrecompileOutcome,
)
from .heuristic_precompiler import PrecompileResult, precompile_heuristic
from .output_validation import (
    is_safe_fallback_directive_rewrite,
    parse_precompiler_output,
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
    "parse_precompiler_output",
    "is_safe_fallback_directive_rewrite",
    "precompile_heuristic",
    "render_prompt",
    "validate_precompiler_output",
]
