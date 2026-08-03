"""Public helpers for safer decision inspection in host-side code."""

from typing import TypeGuard

from .const import DECISION_ERROR, DECISION_NO_DIRECTIVE, DECISION_UPDATE
from .engine import (
    Decision,
    ErrorDecision,
    NoDirectiveDecision,
    State,
    UpdateDecision,
)


def is_update(decision: Decision) -> TypeGuard[UpdateDecision]:
    """Return whether a decision represents a successful state update."""

    return decision["kind"] == DECISION_UPDATE


def is_error(decision: Decision) -> TypeGuard[ErrorDecision]:
    """Return whether a decision represents an error outcome."""

    return decision["kind"] == DECISION_ERROR


def is_no_directive(decision: Decision) -> TypeGuard[NoDirectiveDecision]:
    """Return whether a decision reports that no directive was recognized."""

    return decision["kind"] == DECISION_NO_DIRECTIVE


def get_error_message(decision: Decision) -> str | None:
    """Return the error message for an error decision, if present."""

    if not is_error(decision):
        return None
    return decision["message"]


def get_decision_state(decision: Decision) -> State | None:
    """Return the updated authoritative state for an update decision, if present."""

    if not is_update(decision):
        return None
    return decision["state"]
