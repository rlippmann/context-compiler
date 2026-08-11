"""Deterministic state engine for explicit user directive handling."""

import json
import re
from collections.abc import Mapping
from copy import deepcopy
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
from .grammar import CanonicalDirective, _DirectiveKind, decompose_directive

PolicyValue = Literal["use", "prohibit"]


class _State(TypedDict):
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


class _EvaluatedTransition(TypedDict):
    decision: Decision
    next_state: _State


_NO_DIRECTIVE: Decision = {"kind": DecisionKind.NO_DIRECTIVE, "message": None}


class Engine:
    """Own the authoritative state and apply one directive transition at a time."""

    def __init__(self) -> None:
        self._state: _State
        self._replace_state(_initial_state())

    @property
    def premise(self) -> str | None:
        """Return the current premise from authoritative state."""

        return self._state[STATE_PREMISE]

    @property
    def policies(self) -> Mapping[str, PolicyValue]:
        """Return a defensive copy of the current policy mapping."""

        return deepcopy(self._state[STATE_POLICIES])

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

        Non-canonical input does not produce a state transition and returns
        ``no_directive``. At the current engine boundary, invalid directive
        classification is handled the same way as no-directive input. Accepted
        directives return ``update`` and commit the resulting authoritative
        state before the decision is returned.
        """

        directive = decompose_directive(user_input)
        if not isinstance(directive, CanonicalDirective):
            return _NO_DIRECTIVE.copy()

        return self.apply_directive(directive)

    def apply_directive(self, directive: CanonicalDirective) -> Decision:
        """Evaluate and commit one canonical directive against authoritative state."""

        evaluated = self._evaluate_directive_transition(self._state, directive)
        self._replace_state(evaluated["next_state"])
        return evaluated["decision"]

    def _evaluate_directive_transition(
        self, state: _State, directive: CanonicalDirective
    ) -> _EvaluatedTransition:
        error_decision = self._pre_mutation_error(directive, state=state)
        if error_decision is not None:
            return {"decision": error_decision, "next_state": deepcopy(state)}

        next_state = self._apply_directive(directive, state=state)
        return {"decision": _update_decision(next_state), "next_state": next_state}

    def _replace_state(self, state: _State) -> None:
        self._state = state

    def _pre_mutation_error(
        self, directive: CanonicalDirective, *, state: _State | None = None
    ) -> Decision | None:
        candidate_state = self._state if state is None else state
        # Single error path: all error outcomes are detected before any mutation.
        if directive.kind in {_DirectiveKind.SET_PREMISE, _DirectiveKind.CHANGE_PREMISE}:
            value = directive.operands["value"]
            if _sanitize_premise_value(value) == "":
                if directive.kind is _DirectiveKind.SET_PREMISE:
                    return _error(
                        "Premise value cannot be empty.\n"
                        "Use 'set premise <value>' with a non-empty value."
                    )
                return _error(
                    "Premise value cannot be empty.\n"
                    "Use 'change premise to <value>' with a non-empty value."
                )

        if (
            directive.kind is _DirectiveKind.REMOVE_POLICY
            and _normalize_item(directive.operands["item"]) == ""
        ):
            return _error(
                "Policy item cannot be empty.\nUse 'remove policy <item>' with a non-empty value."
            )

        if (
            directive.kind is _DirectiveKind.USE_ITEM
            and _normalize_item(directive.operands["item"]) == ""
        ):
            return _error("Policy item cannot be empty.\nUse 'use <item>' with a non-empty value.")

        if (
            directive.kind is _DirectiveKind.PROHIBIT_ITEM
            and _normalize_item(directive.operands["item"]) == ""
        ):
            return _error(
                "Policy item cannot be empty.\nUse 'prohibit <item>' with a non-empty value."
            )

        if (
            directive.kind is _DirectiveKind.SET_PREMISE
            and candidate_state[STATE_PREMISE] is not None
        ):
            return _error("Premise already set.\nUse 'change premise to <value>' to modify it.")

        if (
            directive.kind is _DirectiveKind.CHANGE_PREMISE
            and candidate_state[STATE_PREMISE] is None
        ):
            return _error("No premise is set.\nUse 'set premise <value>' to define one.")

        if directive.kind is _DirectiveKind.USE_ITEM:
            item_key = _normalize_item(directive.operands["item"])
            if candidate_state[STATE_POLICIES].get(item_key) == POLICY_PROHIBIT:
                return _error(
                    f'"{item_key}" is currently prohibited.\nRemove or replace it before using it.'
                )

        if directive.kind is _DirectiveKind.PROHIBIT_ITEM:
            item_key = _normalize_item(directive.operands["item"])
            if candidate_state[STATE_POLICIES].get(item_key) == POLICY_USE:
                return _error(
                    f'"{item_key}" is currently in use.\n'
                    "Remove or replace it before prohibiting it."
                )

        if directive.kind is _DirectiveKind.REPLACE_USE:
            new_item = directive.operands["new_item"]
            old_item = directive.operands["old_item"]
            new_key = _normalize_item(new_item)
            old_key = _normalize_item(old_item)
            if new_key == old_key:
                return None

            old_state = candidate_state[STATE_POLICIES].get(old_key)
            new_state = candidate_state[STATE_POLICIES].get(new_key)
            if old_state == POLICY_PROHIBIT:
                return _error(
                    f'"{old_item}" is currently prohibited.\n'
                    "Submit explicit directive(s) to remove it or use a different item."
                )
            if new_state == POLICY_PROHIBIT:
                return _error(
                    f'"{new_item}" is currently prohibited.\n'
                    "Submit explicit directive(s) to remove it or use a different item."
                )
            if old_state not in {None, POLICY_USE}:
                return _error(
                    f'"{old_item}" is not currently in use.\n'
                    "Replacement requires an active 'use' policy."
                )

        return None

    def _apply_directive(self, directive: CanonicalDirective, *, state: _State) -> _State:
        next_state = deepcopy(state)

        if directive.kind is _DirectiveKind.SET_PREMISE:
            next_state[STATE_PREMISE] = _sanitize_premise_value(directive.operands["value"])
            return next_state

        if directive.kind is _DirectiveKind.CHANGE_PREMISE:
            next_state[STATE_PREMISE] = _sanitize_premise_value(directive.operands["value"])
            return next_state

        if directive.kind is _DirectiveKind.USE_ITEM:
            item_key = _normalize_item(directive.operands["item"])
            # Idempotent directives are updates even if state does not change.
            next_state[STATE_POLICIES][item_key] = POLICY_USE
            return next_state

        if directive.kind is _DirectiveKind.PROHIBIT_ITEM:
            item_key = _normalize_item(directive.operands["item"])
            # Idempotent directives are updates even if state does not change.
            next_state[STATE_POLICIES][item_key] = POLICY_PROHIBIT
            return next_state

        if directive.kind is _DirectiveKind.REPLACE_USE:
            self._apply_replacement_explicit(
                next_state,
                directive.operands["new_item"],
                directive.operands["old_item"],
            )
            return next_state

        if directive.kind is _DirectiveKind.REMOVE_POLICY:
            item_key = _normalize_item(directive.operands["item"])
            next_state[STATE_POLICIES].pop(item_key, None)
            return next_state

        if directive.kind is _DirectiveKind.CLEAR_PREMISE:
            next_state[STATE_PREMISE] = None
            return next_state

        if directive.kind is _DirectiveKind.RESET_POLICIES:
            next_state[STATE_POLICIES] = {}
            return next_state

        return _initial_state()

    def _apply_replacement_explicit(self, state: _State, new_item: str, old_item: str) -> None:
        new_key = _normalize_item(new_item)
        old_key = _normalize_item(old_item)

        if new_key == old_key:
            return

        state[STATE_POLICIES].pop(old_key, None)
        state[STATE_POLICIES][new_key] = POLICY_USE


def _initial_state() -> _State:
    return {
        STATE_PREMISE: None,
        STATE_POLICIES: {},
        STATE_VERSION: SCHEMA_VERSION,
    }


def _load_state_json(payload: str) -> _State:
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON payload.") from exc

    return _load_state_obj(raw)


def _load_state_obj(raw: object) -> _State:
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
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _error(message: str) -> Decision:
    return {"kind": DecisionKind.ERROR, "message": message}


def _update_decision(_state: _State) -> Decision:
    return {"kind": DecisionKind.UPDATE, "message": None}
