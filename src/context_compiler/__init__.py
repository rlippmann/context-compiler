from importlib.metadata import version

from .const import POLICY_PROHIBIT, POLICY_USE
from .controller import PreviewResult, StepResult, StructuralDiff, preview, state_diff, step
from .decision_constants import DECISION_CLARIFY, DECISION_PASSTHROUGH, DECISION_UPDATE
from .decision_helpers import (
    get_clarify_prompt,
    get_decision_state,
    is_clarify,
    is_passthrough,
    is_update,
)
from .engine import (
    ApplyResult,
    Checkpoint,
    Decision,
    Engine,
    State,
    Transcript,
    TranscriptMessage,
    compile_transcript,
    create_engine,
    get_policy_items,
    get_premise_value,
)

__version__ = version("context-compiler")

__all__ = [
    "ApplyResult",
    "Checkpoint",
    "Decision",
    "DECISION_CLARIFY",
    "DECISION_PASSTHROUGH",
    "DECISION_UPDATE",
    "Engine",
    "POLICY_PROHIBIT",
    "POLICY_USE",
    "PreviewResult",
    "State",
    "StepResult",
    "StructuralDiff",
    "Transcript",
    "TranscriptMessage",
    "compile_transcript",
    "create_engine",
    "get_clarify_prompt",
    "get_decision_state",
    "get_premise_value",
    "get_policy_items",
    "is_clarify",
    "is_passthrough",
    "is_update",
    "preview",
    "state_diff",
    "step",
]
