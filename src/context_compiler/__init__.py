from importlib.metadata import version

from .const import (
    DECISION_ERROR,
    DECISION_NO_DIRECTIVE,
    DECISION_UPDATE,
    POLICY_PROHIBIT,
    POLICY_USE,
)
from .decision_helpers import (
    get_error_message,
    is_error,
    is_no_directive,
    is_update,
)
from .engine import (
    Decision,
    DecisionKind,
    Engine,
    PolicyValue,
    State,
    create_engine,
)

__version__ = version("context-compiler")

__all__ = [
    "Decision",
    "DecisionKind",
    "DECISION_ERROR",
    "DECISION_NO_DIRECTIVE",
    "DECISION_UPDATE",
    "Engine",
    "POLICY_PROHIBIT",
    "POLICY_USE",
    "PolicyValue",
    "State",
    "create_engine",
    "get_error_message",
    "is_error",
    "is_no_directive",
    "is_update",
]
