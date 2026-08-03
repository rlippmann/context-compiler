"""Public helpers for safer decision inspection in host-side code."""

from typing import TypeGuard

from .engine import (
    Decision,
    ErrorDecision,
    NoDirectiveDecision,
    State,
    UpdateDecision,
)


def is_update(decision: Decision) -> TypeGuard[UpdateDecision]:
    return decision["kind"] == "update"


def is_error(decision: Decision) -> TypeGuard[ErrorDecision]:
    return decision["kind"] == "error"


def is_no_directive(decision: Decision) -> TypeGuard[NoDirectiveDecision]:
    return decision["kind"] == "no_directive"


def get_error_message(decision: Decision) -> str | None:
    if not is_error(decision):
        return None
    return decision["message"]


def get_decision_state(decision: Decision) -> State | None:
    if not is_update(decision):
        return None
    return decision["state"]
