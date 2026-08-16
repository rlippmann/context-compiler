"""Deterministic state engine for explicit user directive handling."""

import json
import re
from collections.abc import Mapping
from copy import deepcopy
from types import MappingProxyType
from typing import Literal, TypedDict
from unicodedata import normalize as unicode_normalize

from .const import (
    POLICY_PROHIBIT,
    POLICY_USE,
    SCHEMA_VERSION,
    STATE_POLICIES,
    STATE_PREMISE,
    STATE_VERSION,
)
from .decision import (
    NoDirectiveDecision,
    SemanticErrorDecision,
    SemanticFailure,
    UpdateDecision,
)
from .grammar import CanonicalDirective, DirectiveKind, decompose_directive

PolicyValue = Literal["use", "prohibit"]


class _State(TypedDict):
    """Versioned authoritative state."""

    premise: str | None
    policies: dict[str, PolicyValue]
    version: Literal[2]


class _EvaluatedTransition(TypedDict):
    decision: UpdateDecision | SemanticErrorDecision
    next_state: _State


_NO_DIRECTIVE = NoDirectiveDecision()


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

    def step(self, user_input: str) -> NoDirectiveDecision | UpdateDecision | SemanticErrorDecision:
        """Evaluate and commit one user input against authoritative state.

        Non-canonical input does not produce a state transition and returns
        ``NoDirectiveDecision``. At the current engine boundary, invalid
        directive classification is handled the same way as no-directive
        input. Accepted canonical directives delegate to
        ``apply_directive(...)`` and return ``UpdateDecision`` or
        ``SemanticErrorDecision`` after the state transition is evaluated.
        """

        directive = decompose_directive(user_input)
        if not isinstance(directive, CanonicalDirective):
            return _NO_DIRECTIVE

        return self.apply_directive(directive)

    def apply_directive(
        self, directive: CanonicalDirective
    ) -> UpdateDecision | SemanticErrorDecision:
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
        return {
            "decision": _update_decision(state, next_state),
            "next_state": next_state,
        }

    def _replace_state(self, state: _State) -> None:
        self._state = state

    def _pre_mutation_error(
        self, directive: CanonicalDirective, *, state: _State | None = None
    ) -> SemanticErrorDecision | None:
        candidate_state = self._state if state is None else state
        # Single error path: all error outcomes are detected before any mutation.
        if (
            directive.kind is DirectiveKind.SET_PREMISE
            and candidate_state[STATE_PREMISE] is not None
        ):
            return _error(
                failure=SemanticFailure.PREMISE_ALREADY_SET,
                directive=directive,
                repairs=(_repair_change_premise(directive.operands["value"]),),
            )

        if (
            directive.kind is DirectiveKind.CHANGE_PREMISE
            and candidate_state[STATE_PREMISE] is None
        ):
            return _error(
                failure=SemanticFailure.PREMISE_NOT_SET,
                directive=directive,
                repairs=(_repair_set_premise(directive.operands["value"]),),
            )

        if directive.kind is DirectiveKind.USE_ITEM:
            item_key = _normalize_item(directive.operands["item"])
            if candidate_state[STATE_POLICIES].get(item_key) == POLICY_PROHIBIT:
                return _error(
                    failure=SemanticFailure.ITEM_PROHIBITED,
                    directive=directive,
                    repairs=(
                        _repair_remove_policy(directive.operands["item"]),
                        _repair_use_item(directive.operands["item"]),
                    ),
                )

        if directive.kind is DirectiveKind.PROHIBIT_ITEM:
            item_key = _normalize_item(directive.operands["item"])
            if candidate_state[STATE_POLICIES].get(item_key) == POLICY_USE:
                return _error(
                    failure=SemanticFailure.ITEM_ALREADY_IN_USE,
                    directive=directive,
                    repairs=(
                        _repair_remove_policy(directive.operands["item"]),
                        _repair_prohibit_item(directive.operands["item"]),
                    ),
                )

        if directive.kind is DirectiveKind.REPLACE_USE:
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
                    failure=SemanticFailure.REPLACEMENT_SOURCE_PROHIBITED,
                    directive=directive,
                    repairs=(),
                )
            if new_state == POLICY_PROHIBIT:
                return _error(
                    failure=SemanticFailure.REPLACEMENT_TARGET_PROHIBITED,
                    directive=directive,
                    repairs=(
                        _repair_remove_policy(new_item),
                        directive,
                    ),
                )
            if old_state != POLICY_USE:
                return _error(
                    failure=SemanticFailure.REPLACEMENT_SOURCE_MISSING,
                    directive=directive,
                    repairs=(),
                )

        return None

    def _apply_directive(self, directive: CanonicalDirective, *, state: _State) -> _State:
        next_state = deepcopy(state)

        if directive.kind is DirectiveKind.SET_PREMISE:
            next_state[STATE_PREMISE] = _sanitize_premise_value(directive.operands["value"])
            return next_state

        if directive.kind is DirectiveKind.CHANGE_PREMISE:
            next_state[STATE_PREMISE] = _sanitize_premise_value(directive.operands["value"])
            return next_state

        if directive.kind is DirectiveKind.USE_ITEM:
            item_key = _normalize_item(directive.operands["item"])
            # Idempotent directives are updates even if state does not change.
            next_state[STATE_POLICIES][item_key] = POLICY_USE
            return next_state

        if directive.kind is DirectiveKind.PROHIBIT_ITEM:
            item_key = _normalize_item(directive.operands["item"])
            # Idempotent directives are updates even if state does not change.
            next_state[STATE_POLICIES][item_key] = POLICY_PROHIBIT
            return next_state

        if directive.kind is DirectiveKind.REPLACE_USE:
            self._apply_replacement_explicit(
                next_state,
                directive.operands["new_item"],
                directive.operands["old_item"],
            )
            return next_state

        if directive.kind is DirectiveKind.REMOVE_POLICY:
            item_key = _normalize_item(directive.operands["item"])
            next_state[STATE_POLICIES].pop(item_key, None)
            return next_state

        if directive.kind is DirectiveKind.CLEAR_PREMISE:
            next_state[STATE_PREMISE] = None
            return next_state

        if directive.kind is DirectiveKind.RESET_POLICIES:
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

    sanitized_premise = None if premise is None else _sanitize_premise_value(premise)
    if premise is not None and sanitized_premise == "":
        raise ValueError("Invalid state payload.")

    normalized_policies: dict[str, PolicyValue] = {}
    seen_policy_sources: dict[str, str] = {}
    for key, value in policies.items():
        if not isinstance(key, str):
            raise ValueError("Invalid state payload.")
        if value not in {POLICY_USE, POLICY_PROHIBIT}:
            raise ValueError("Invalid state payload.")
        normalized_key = _normalize_item(key)
        if normalized_key == "":
            raise ValueError("Invalid state payload.")
        prior_source = seen_policy_sources.get(normalized_key)
        if prior_source is not None and prior_source != key:
            raise ValueError("Invalid state payload.")
        seen_policy_sources[normalized_key] = key
        normalized_policies[normalized_key] = value

    return {
        STATE_PREMISE: sanitized_premise,
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
    normalized = normalized.casefold()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _error(
    failure: SemanticFailure,
    directive: CanonicalDirective,
    repairs: tuple[CanonicalDirective, ...],
) -> SemanticErrorDecision:
    return SemanticErrorDecision(failure=failure, directive=directive, repairs=repairs)


def _repair_remove_policy(item: str) -> CanonicalDirective:
    return CanonicalDirective(
        kind=DirectiveKind.REMOVE_POLICY,
        operands=MappingProxyType({"item": item}),
    )


def _repair_use_item(item: str) -> CanonicalDirective:
    return CanonicalDirective(
        kind=DirectiveKind.USE_ITEM,
        operands=MappingProxyType({"item": item}),
    )


def _repair_prohibit_item(item: str) -> CanonicalDirective:
    return CanonicalDirective(
        kind=DirectiveKind.PROHIBIT_ITEM,
        operands=MappingProxyType({"item": item}),
    )


def _repair_change_premise(value: str) -> CanonicalDirective:
    return CanonicalDirective(
        kind=DirectiveKind.CHANGE_PREMISE,
        operands=MappingProxyType({"value": value}),
    )


def _repair_set_premise(value: str) -> CanonicalDirective:
    return CanonicalDirective(
        kind=DirectiveKind.SET_PREMISE,
        operands=MappingProxyType({"value": value}),
    )


def _update_decision(previous_state: _State, next_state: _State) -> UpdateDecision:
    return UpdateDecision(changed=previous_state != next_state)
