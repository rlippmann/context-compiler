"""Public auditability helpers layered above the authoritative engine."""

from .controller import (
    PreviewResult,
    StructuralDiff,
    diff_has_changes,
    get_preview_decision,
    get_preview_state_after,
    preview,
    preview_would_mutate,
    state_diff,
)

__all__ = [
    "PreviewResult",
    "StructuralDiff",
    "diff_has_changes",
    "get_preview_decision",
    "get_preview_state_after",
    "preview",
    "preview_would_mutate",
    "state_diff",
]
