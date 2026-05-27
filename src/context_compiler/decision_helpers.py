"""Public helpers for safer decision inspection in host-side code."""

from .decision_constants import DECISION_CLARIFY, DECISION_PASSTHROUGH, DECISION_UPDATE
from .engine import Decision, State


def is_update(decision: Decision) -> bool:
    return decision["kind"] == DECISION_UPDATE


def is_clarify(decision: Decision) -> bool:
    return decision["kind"] == DECISION_CLARIFY


def is_passthrough(decision: Decision) -> bool:
    return decision["kind"] == DECISION_PASSTHROUGH


def get_clarify_prompt(decision: Decision) -> str | None:
    return decision["prompt_to_user"]


def get_decision_state(decision: Decision) -> State | None:
    return decision["state"]
