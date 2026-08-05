from importlib.metadata import version

from .const import (
    DECISION_ERROR,
    DECISION_NO_DIRECTIVE,
    DECISION_UPDATE,
    POLICY_PROHIBIT,
    POLICY_USE,
)
from .controller import (
    StepResult,
    get_step_decision,
    get_step_state,
    step,
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
    "StepResult",
    "create_engine",
    "get_error_message",
    "get_step_decision",
    "get_step_state",
    "is_error",
    "is_no_directive",
    "is_update",
    "step",
]
