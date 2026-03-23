"""Deterministic state engine for explicit user directive handling."""

import json
from copy import deepcopy
from enum import StrEnum
from typing import Literal, TypedDict

from .const import (
    POLICY_PROHIBIT,
    POLICY_USE,
    SCHEMA_VERSION,
    STATE_POLICIES,
    STATE_PREMISE,
    STATE_VERSION,
)

PolicyValue = Literal["use", "prohibit"]


class State(TypedDict):
    """Versioned authoritative state."""

    premise: str | None
    policies: dict[str, PolicyValue]
    version: Literal[2]


class DecisionKind(StrEnum):
    UPDATE = "update"
    PASSTHROUGH = "passthrough"
    CLARIFY = "clarify"


class Decision(TypedDict):
    kind: DecisionKind
    state: State | None
    prompt_to_user: str | None


class ApplyResultState(TypedDict):
    kind: Literal["state"]
    state: State


class ApplyResultConfirm(TypedDict):
    kind: Literal["confirm"]
    prompt_to_user: str


ApplyResult = ApplyResultState | ApplyResultConfirm

_PASSTHROUGH: Decision = {
    "kind": DecisionKind.PASSTHROUGH,
    "state": None,
    "prompt_to_user": None,
}


def create_engine(state: State | None = None) -> "Engine":
    return Engine(state=state)


def compile_transcript(messages: list[dict[str, object]]) -> ApplyResult:
    engine = create_engine()
    return engine.apply_transcript(messages)


def get_premise_value(state: State) -> str | None:
    return state[STATE_PREMISE]


def get_focus_value(state: State) -> str | None:
    return get_premise_value(state)


def get_policy_items(state: State, value: PolicyValue | None = None) -> list[str]:
    if value is None:
        return sorted(state[STATE_POLICIES].keys())
    return sorted(k for k, v in state[STATE_POLICIES].items() if v == value)


def get_prohibited_items(state: State) -> list[str]:
    return get_policy_items(state, POLICY_PROHIBIT)


class Engine:
    def __init__(self, state: State | None = None) -> None:
        self._state: State
        self._pending_prompt: str | None = None
        self._replace_state(_initial_state() if state is None else _load_state_obj(state))

    @property
    def state(self) -> State:
        return deepcopy(self._state)

    def export_json(self) -> str:
        return json.dumps(self._state, sort_keys=True, separators=(",", ":"))

    def import_json(self, payload: str) -> None:
        self._replace_state(_load_state_json(payload))

    def step(self, user_input: str) -> Decision:
        del user_input
        return _PASSTHROUGH.copy()

    def apply_transcript(self, messages: list[dict[str, object]]) -> ApplyResult:
        for content in _iter_user_contents(messages):
            decision = self.step(content)
            if decision["kind"] == DecisionKind.CLARIFY:
                prompt = decision["prompt_to_user"]
                assert prompt is not None
                return {"kind": "confirm", "prompt_to_user": prompt}

        return {"kind": "state", "state": self.state}

    def _replace_state(self, state: State) -> None:
        self._state = state
        self._pending_prompt = None


def _initial_state() -> State:
    return {
        STATE_PREMISE: None,
        STATE_POLICIES: {},
        STATE_VERSION: SCHEMA_VERSION,
    }


def _iter_user_contents(messages: list[dict[str, object]]) -> list[str]:
    user_contents: list[str] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role == "user" and isinstance(content, str):
            user_contents.append(content)
    return user_contents


def _load_state_json(payload: str) -> State:
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON payload.") from exc

    return _load_state_obj(raw)


def _load_state_obj(raw: object) -> State:
    if not isinstance(raw, dict):
        raise ValueError("Invalid state payload.")

    if set(raw.keys()) != {STATE_PREMISE, STATE_POLICIES, STATE_VERSION}:
        raise ValueError("Invalid state payload.")

    if raw[STATE_VERSION] != SCHEMA_VERSION:
        raise ValueError(f"Unsupported state version: {raw[STATE_VERSION]!r}")

    premise = raw[STATE_PREMISE]
    policies = raw[STATE_POLICIES]

    if premise is not None and not isinstance(premise, str):
        raise ValueError("Invalid state payload.")
    if not isinstance(policies, dict):
        raise ValueError("Invalid state payload.")

    normalized_policies: dict[str, PolicyValue] = {}
    for key, value in policies.items():
        if not isinstance(key, str):
            raise ValueError("Invalid state payload.")
        if value not in {POLICY_USE, POLICY_PROHIBIT}:
            raise ValueError("Invalid state payload.")
        normalized_policies[key] = value

    return {
        STATE_PREMISE: premise,
        STATE_POLICIES: dict(sorted(normalized_policies.items())),
        STATE_VERSION: SCHEMA_VERSION,
    }
