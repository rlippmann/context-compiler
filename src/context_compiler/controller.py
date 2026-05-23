"""Stateless controller helpers layered above the authoritative engine."""

from typing import Literal, TypedDict

from .engine import Decision, Engine, State

OUTPUT_VERSION: Literal[1] = 1


class PremiseDiff(TypedDict):
    before: str | None
    after: str | None
    changed: bool


class ChangedPolicyDiff(TypedDict):
    before: Literal["use", "prohibit"]
    after: Literal["use", "prohibit"]


class PoliciesDiff(TypedDict):
    added: dict[str, Literal["use", "prohibit"]]
    removed: dict[str, Literal["use", "prohibit"]]
    changed: dict[str, ChangedPolicyDiff]


class StructuralDiff(TypedDict):
    changed: bool
    premise: PremiseDiff
    policies: PoliciesDiff


class StepResult(TypedDict):
    output_version: Literal[1]
    mode: Literal["step"]
    decision: Decision
    state: State


class PreviewResult(TypedDict):
    output_version: Literal[1]
    mode: Literal["preview"]
    decision: Decision
    state_before: State
    state_after: State
    diff: StructuralDiff
    would_mutate: bool


def state_diff(before: State, after: State) -> StructuralDiff:
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
    decision = engine.step(user_input)
    return {
        "output_version": OUTPUT_VERSION,
        "mode": "step",
        "decision": decision,
        "state": engine.state,
    }


def preview(engine: Engine, user_input: str) -> PreviewResult:
    checkpoint = engine.export_checkpoint()
    state_before = engine.state

    decision: Decision | None = None
    state_after: State | None = None
    try:
        decision = engine.step(user_input)
        state_after = engine.state
    finally:
        engine.import_checkpoint(checkpoint)

    assert decision is not None
    assert state_after is not None

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
