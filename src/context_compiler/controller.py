"""Stateless controller helpers layered above the authoritative engine."""

from typing import Literal, TypedDict

from .engine import Decision, Engine, State

OUTPUT_VERSION: Literal[1] = 1


class PremiseDiff(TypedDict):
    """Describe how the authoritative premise changed between two states."""

    before: str | None
    after: str | None
    changed: bool


class ChangedPolicyDiff(TypedDict):
    """Capture the old and new value for one policy item."""

    before: Literal["use", "prohibit"]
    after: Literal["use", "prohibit"]


class PoliciesDiff(TypedDict):
    """Summarize policy items added, removed, or changed between two states."""

    added: dict[str, Literal["use", "prohibit"]]
    removed: dict[str, Literal["use", "prohibit"]]
    changed: dict[str, ChangedPolicyDiff]


class StructuralDiff(TypedDict):
    """Describe whether and how authoritative state changed structurally."""

    changed: bool
    premise: PremiseDiff
    policies: PoliciesDiff


class StepResult(TypedDict):
    """Return the committed outcome of one controller-driven engine step."""

    output_version: Literal[1]
    mode: Literal["step"]
    decision: Decision
    state: State


class PreviewResult(TypedDict):
    """Return the dry-run outcome of one controller preview evaluation."""

    output_version: Literal[1]
    mode: Literal["preview"]
    decision: Decision
    state_before: State
    state_after: State
    diff: StructuralDiff
    would_mutate: bool


def get_step_decision(step_result: StepResult) -> Decision:
    """Return the decision emitted by a committed controller step."""

    return step_result["decision"]


def get_step_state(step_result: StepResult) -> State:
    """Return the authoritative state after a committed controller step."""

    return step_result["state"]


def get_preview_decision(preview_result: PreviewResult) -> Decision:
    """Return the decision that preview computed without mutating live state."""

    return preview_result["decision"]


def get_preview_state_after(preview_result: PreviewResult) -> State:
    """Return the simulated post-transition state from preview."""

    return preview_result["state_after"]


def preview_would_mutate(preview_result: PreviewResult) -> bool:
    """Return whether preview observed any structural state change."""

    return preview_result["would_mutate"]


def diff_has_changes(diff: StructuralDiff) -> bool:
    """Return whether a structural diff reports any state change."""

    return diff["changed"]


def state_diff(before: State, after: State) -> StructuralDiff:
    """Compute a structural diff between two authoritative engine states."""

    before_premise = before["premise"]
    after_premise = after["premise"]
    premise_changed = before_premise != after_premise

    before_policies = before["policies"]
    after_policies = after["policies"]

    added: dict[str, Literal["use", "prohibit"]] = {}
    removed: dict[str, Literal["use", "prohibit"]] = {}
    changed: dict[str, ChangedPolicyDiff] = {}

    for key, value in after_policies.items():
        if key not in before_policies:
            added[key] = value
            continue
        before_value = before_policies[key]
        if before_value != value:
            changed[key] = {"before": before_value, "after": value}

    for key, value in before_policies.items():
        if key not in after_policies:
            removed[key] = value

    any_policy_change = bool(added or removed or changed)
    return {
        "changed": premise_changed or any_policy_change,
        "premise": {
            "before": before_premise,
            "after": after_premise,
            "changed": premise_changed,
        },
        "policies": {
            "added": added,
            "removed": removed,
            "changed": changed,
        },
    }


def step(engine: Engine, user_input: str) -> StepResult:
    """Commit one engine transition and package the resulting decision and state."""

    decision = engine.step(user_input)
    return {
        "output_version": OUTPUT_VERSION,
        "mode": "step",
        "decision": decision,
        "state": engine.state,
    }


def preview(engine: Engine, user_input: str) -> PreviewResult:
    """Evaluate one transition without mutating the engine's live state.

    Preview uses the same transition evaluation path as committed execution,
    then returns the simulated decision, before/after states, and a structural
    diff that callers can inspect before deciding whether to step.
    """

    state_before = engine.state
    # Preview intentionally consumes the engine's private evaluator so preview and
    # committed execution share one transition path without making evaluation public.
    evaluated = engine._evaluate_transition(state_before, user_input)  # noqa: SLF001
    decision = evaluated.decision
    state_after = evaluated.next_state

    diff = state_diff(state_before, state_after)
    would_mutate = diff["changed"]
    return {
        "output_version": OUTPUT_VERSION,
        "mode": "preview",
        "decision": decision,
        "state_before": state_before,
        "state_after": state_after,
        "diff": diff,
        "would_mutate": would_mutate,
    }
