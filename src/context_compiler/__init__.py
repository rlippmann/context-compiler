from importlib.metadata import version

from .controller import PreviewResult, StepResult, StructuralDiff, preview, state_diff, step
from .decision_constants import DECISION_CLARIFY, DECISION_PASSTHROUGH, DECISION_UPDATE
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
    "PreviewResult",
    "State",
    "StepResult",
    "StructuralDiff",
    "Transcript",
    "TranscriptMessage",
    "compile_transcript",
    "create_engine",
    "get_premise_value",
    "get_policy_items",
    "preview",
    "state_diff",
    "step",
]
