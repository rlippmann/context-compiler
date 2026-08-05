"""Deterministic state engine for explicit user directive handling."""

import json
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, TypedDict
from unicodedata import normalize as unicode_normalize

from .const import (
    DECISION_ERROR,
    DECISION_NO_DIRECTIVE,
    DECISION_UPDATE,
    POLICY_PROHIBIT,
    POLICY_USE,
    SCHEMA_VERSION,
    STATE_POLICIES,
    STATE_PREMISE,
    STATE_VERSION,
)
from .grammar import DirectiveKind, decompose_directive

PolicyValue = Literal["use", "prohibit"]


class State(TypedDict):
    """Versioned authoritative state."""

    premise: str | None
    policies: dict[str, PolicyValue]
    version: Literal[2]


class DecisionKind(StrEnum):
    """Public decision-kind vocabulary for host-side branching."""

    NO_DIRECTIVE = DECISION_NO_DIRECTIVE
    UPDATE = DECISION_UPDATE
    ERROR = DECISION_ERROR


class Decision(TypedDict):
    """Report one deterministic engine outcome to host-side callers."""

    kind: DecisionKind
    message: str | None


@dataclass(frozen=True)
class Action:
    """Represent one parsed engine action before state validation or mutation."""

    kind: Literal[
        "set_premise",
        "change_premise",
        "use_item",
        "prohibit_item",
        "remove_policy_item",
        "replace_use",
        "clear_premise",
        "reset_policies",
        "clear_state",
    ]
    value: str | None = None
    item: str | None = None
    new_item: str | None = None
    old_item: str | None = None


@dataclass(frozen=True)
class _EvaluatedTransition:
    decision: Decision
    next_state: State


_NO_DIRECTIVE: Decision = {"kind": DecisionKind.NO_DIRECTIVE, "message": None}


def create_engine(state: State | None = None) -> "Engine":
    """Create an engine initialized from validated state or the empty state."""

    return Engine(state=state)


class Engine:
    """Own the authoritative state and apply one directive transition at a time."""

    def __init__(self, state: State | None = None) -> None:
        self._state: State
        self._replace_state(_initial_state() if state is None else _load_state_obj(state))

    @property
    def premise(self) -> str | None:
        """Return the current premise from authoritative state."""

        return self._state[STATE_PREMISE]

    @property
    def policies(self) -> Mapping[str, PolicyValue]:
        """Return a defensive copy of the current policy mapping."""

        return deepcopy(self._state[STATE_POLICIES])

    @property
    def state(self) -> State:
        """Return a defensive copy of the full authoritative state."""

        return deepcopy(self._state)

    def export_json(self) -> str:
        """Serialize the current authoritative state to canonical JSON text."""

        return json.dumps(self._state, sort_keys=True, separators=(",", ":"))

    def import_json(self, payload: str) -> None:
        """Replace authoritative state from previously exported JSON text.

        The payload must match the current state schema and is normalized using
        the same validation rules applied to other engine state inputs.
        """

        self._replace_state(_load_state_json(payload))

    def step(self, user_input: str) -> Decision:
        """Evaluate and commit one user input against authoritative state.

        Non-directive input returns ``no_directive`` without changing state.
        Invalid directives return ``error`` without changing state. Accepted
        directives return ``update`` and commit the resulting authoritative
        state before the decision is returned.
        """

        evaluated = self._evaluate_transition(self._state, user_input)
        self._replace_state(evaluated.next_state)
        return evaluated.decision

    def _evaluate_transition(self, state: State, user_input: str) -> _EvaluatedTransition:
        action = _parse_directive(user_input)
        if action is None:
            return _EvaluatedTransition(decision=_NO_DIRECTIVE.copy(), next_state=deepcopy(state))

        error_decision = self._pre_mutation_error(action, state=state)
        if error_decision is not None:
            return _EvaluatedTransition(decision=error_decision, next_state=deepcopy(state))

        next_state = self._apply_action(action, state=state)
        return _EvaluatedTransition(decision=_update_decision(next_state), next_state=next_state)

    def _replace_state(self, state: State) -> None:
        self._state = state

    def _pre_mutation_error(self, action: Action, *, state: State | None = None) -> Decision | None:
        candidate_state = self._state if state is None else state
        # Single error path: all error outcomes are detected before any mutation.
        if action.kind in {"set_premise", "change_premise"}:
            assert action.value is not None
            if _sanitize_premise_value(action.value) == "":
                if action.kind == "set_premise":
                    return _error(
                        "Premise value cannot be empty.\n"
                        "Use 'set premise <value>' with a non-empty value."
                    )
                return _error(
                    "Premise value cannot be empty.\n"
                    "Use 'change premise to <value>' with a non-empty value."
                )

        if action.kind == "remove_policy_item":
            assert action.item is not None
            if _normalize_item(action.item) == "":
                return _error(
                    "Policy item cannot be empty.\n"
                    "Use 'remove policy <item>' with a non-empty value."
                )

        if action.kind == "use_item":
            assert action.item is not None
            if _normalize_item(action.item) == "":
                return _error(
                    "Policy item cannot be empty.\nUse 'use <item>' with a non-empty value."
                )

        if action.kind == "prohibit_item":
            assert action.item is not None
            if _normalize_item(action.item) == "":
                return _error(
                    "Policy item cannot be empty.\nUse 'prohibit <item>' with a non-empty value."
                )

        if action.kind == "set_premise" and candidate_state[STATE_PREMISE] is not None:
            return _error("Premise already set.\nUse 'change premise to <value>' to modify it.")

        if action.kind == "change_premise" and candidate_state[STATE_PREMISE] is None:
            return _error("No premise is set.\nUse 'set premise <value>' to define one.")

        if action.kind == "use_item":
            assert action.item is not None
            item_key = _normalize_item(action.item)
            if candidate_state[STATE_POLICIES].get(item_key) == POLICY_PROHIBIT:
                return _error(
                    f'"{item_key}" is currently prohibited.\nRemove or replace it before using it.'
                )

        if action.kind == "prohibit_item":
            assert action.item is not None
            item_key = _normalize_item(action.item)
            if candidate_state[STATE_POLICIES].get(item_key) == POLICY_USE:
                return _error(
                    f'"{item_key}" is currently in use.\n'
                    "Remove or replace it before prohibiting it."
                )

        if action.kind == "replace_use":
            assert action.new_item is not None
            assert action.old_item is not None
            new_key = _normalize_item(action.new_item)
            old_key = _normalize_item(action.old_item)
            if new_key == old_key:
                return None

            old_state = candidate_state[STATE_POLICIES].get(old_key)
            new_state = candidate_state[STATE_POLICIES].get(new_key)
            if old_state == POLICY_PROHIBIT:
                return _error(
                    f'"{action.old_item}" is currently prohibited.\n'
                    "Submit explicit directive(s) to remove it or use a different item."
                )
            if new_state == POLICY_PROHIBIT:
                return _error(
                    f'"{action.new_item}" is currently prohibited.\n'
                    "Submit explicit directive(s) to remove it or use a different item."
                )
            if old_state not in {None, POLICY_USE}:
                return _error(
                    f'"{action.old_item}" is not currently in use.\n'
                    "Replacement requires an active 'use' policy."
                )

        return None

    def _apply_action(self, action: Action, *, state: State) -> State:
        next_state = deepcopy(state)
        kind = action.kind

        if kind == "set_premise":
            assert action.value is not None
            next_state[STATE_PREMISE] = _sanitize_premise_value(action.value)
            return next_state

        if kind == "change_premise":
            assert action.value is not None
            next_state[STATE_PREMISE] = _sanitize_premise_value(action.value)
            return next_state

        if kind == "use_item":
            assert action.item is not None
            item_key = _normalize_item(action.item)
            # Idempotent directives are updates even if state does not change.
            next_state[STATE_POLICIES][item_key] = POLICY_USE
            return next_state

        if kind == "prohibit_item":
            assert action.item is not None
            item_key = _normalize_item(action.item)
            # Idempotent directives are updates even if state does not change.
            next_state[STATE_POLICIES][item_key] = POLICY_PROHIBIT
            return next_state

        if kind == "replace_use":
            assert action.new_item is not None
            assert action.old_item is not None
            self._apply_replacement_explicit(next_state, action.new_item, action.old_item)
            return next_state

        if kind == "remove_policy_item":
            assert action.item is not None
            item_key = _normalize_item(action.item)
            next_state[STATE_POLICIES].pop(item_key, None)
            return next_state

        if kind == "clear_premise":
            next_state[STATE_PREMISE] = None
            return next_state

        if kind == "reset_policies":
            next_state[STATE_POLICIES] = {}
            return next_state

        return _initial_state()

    def _apply_replacement_explicit(self, state: State, new_item: str, old_item: str) -> None:
        new_key = _normalize_item(new_item)
        old_key = _normalize_item(old_item)

        if new_key == old_key:
            return

        state[STATE_POLICIES].pop(old_key, None)
        state[STATE_POLICIES][new_key] = POLICY_USE


def _parse_directive(user_input: str) -> Action | None:
    parsed = decompose_directive(user_input)
    if parsed is None:
        return None

    if parsed.kind is DirectiveKind.SET_PREMISE:
        return Action(kind="set_premise", value=parsed.operands["value"])
    if parsed.kind is DirectiveKind.CHANGE_PREMISE:
        return Action(kind="change_premise", value=parsed.operands["value"])
    if parsed.kind is DirectiveKind.USE_ITEM:
        return Action(kind="use_item", item=parsed.operands["item"])
    if parsed.kind is DirectiveKind.PROHIBIT_ITEM:
        return Action(kind="prohibit_item", item=parsed.operands["item"])
    if parsed.kind is DirectiveKind.REMOVE_POLICY:
        return Action(kind="remove_policy_item", item=parsed.operands["item"])
    if parsed.kind is DirectiveKind.REPLACE_USE:
        return Action(
            kind="replace_use",
            new_item=parsed.operands["new_item"],
            old_item=parsed.operands["old_item"],
        )
    if parsed.kind is DirectiveKind.CLEAR_PREMISE:
        return Action(kind="clear_premise")
    if parsed.kind is DirectiveKind.RESET_POLICIES:
        return Action(kind="reset_policies")
    return Action(kind="clear_state")


def _initial_state() -> State:
    return {
        STATE_PREMISE: None,
        STATE_POLICIES: {},
        STATE_VERSION: SCHEMA_VERSION,
    }


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
        normalized_key = _normalize_item(key)
        if normalized_key == "":
            raise ValueError("Invalid state payload.")
        if _normalize_item(normalized_key) != normalized_key:
            raise ValueError("Invalid state payload.")
        normalized_policies[normalized_key] = value

    return {
        STATE_PREMISE: None if premise is None else _sanitize_premise_value(premise),
        STATE_POLICIES: dict(sorted(normalized_policies.items())),
        STATE_VERSION: SCHEMA_VERSION,
    }


def _sanitize_premise_value(value: str) -> str:
    sanitized = unicode_normalize("NFKC", value)
    sanitized = sanitized.replace("’", "'").replace("`", "'")
    return re.sub(r"\s+", " ", sanitized).strip()


def _normalize_item(value: str) -> str:
    normalized = unicode_normalize("NFKC", value)
    normalized = normalized.replace("’", "'").replace("`", "'")
    normalized = normalized.lower()
    normalized = re.sub(r"\bdont\b", "don't", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"^(?:a|an|the)\b\s*", "", normalized)
    return normalized.strip()


def _error(message: str) -> Decision:
    return {"kind": DecisionKind.ERROR, "message": message}


def _update_decision(_state: State) -> Decision:
    return {"kind": DecisionKind.UPDATE, "message": None}
