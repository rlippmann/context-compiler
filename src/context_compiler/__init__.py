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
    get_decision_state,
    get_error_message,
    is_error,
    is_no_directive,
    is_update,
)
from .engine import (
    Decision,
    Engine,
    ErrorDecision,
    NoDirectiveDecision,
    PolicyValue,
    State,
    UpdateDecision,
    create_engine,
)

__version__ = version("context-compiler")

__all__ = [
    "Decision",
    "DECISION_ERROR",
    "DECISION_NO_DIRECTIVE",
    "DECISION_UPDATE",
    "ErrorDecision",
    "Engine",
    "NoDirectiveDecision",
    "POLICY_PROHIBIT",
    "POLICY_USE",
    "PolicyValue",
    "State",
    "StepResult",
    "UpdateDecision",
    "create_engine",
    "get_error_message",
    "get_decision_state",
    "get_step_decision",
    "get_step_state",
    "is_error",
    "is_no_directive",
    "is_update",
    "step",
]
