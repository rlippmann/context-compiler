from importlib.metadata import version

from .const import (
    DECISION_ERROR,
    DECISION_NO_DIRECTIVE,
    DECISION_UPDATE,
    POLICY_PROHIBIT,
    POLICY_USE,
)
from .decision import (
    Decision,
    DecisionKind,
    NoDirectiveDecision,
    SemanticErrorDecision,
    SemanticFailure,
    UpdateDecision,
)
from .engine import Engine, PolicyValue

__version__ = version("context-compiler")

__all__ = [
    "Decision",
    "DecisionKind",
    "NoDirectiveDecision",
    "SemanticErrorDecision",
    "SemanticFailure",
    "UpdateDecision",
    "DECISION_ERROR",
    "DECISION_NO_DIRECTIVE",
    "DECISION_UPDATE",
    "Engine",
    "POLICY_PROHIBIT",
    "POLICY_USE",
    "PolicyValue",
]
