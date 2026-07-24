"""Deterministic state engine for explicit user directive handling."""

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
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
from .grammar import DirectiveKind
from .grammar import _parse_directive as _parse_canonical_directive

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


@dataclass(frozen=True)
class Action:
    kind: Literal[
        "compound_directive_invalid",
        "set_premise",
        "change_premise",
        "use_item",
        "prohibit_item",
        "remove_policy_item",
        "replace_use",
        "replace_use_incomplete",
        "clear_premise",
        "reset_policies",
        "clear_state",
    ]
    value: str | None = None
    item: str | None = None
    new_item: str | None = None
    old_item: str | None = None


_PASSTHROUGH: Decision = {
    "kind": DecisionKind.PASSTHROUGH,
    "state": None,
    "prompt_to_user": None,
}

_AFFIRMATIVE_CONFIRMATIONS = {"yes", "yes please", "yep", "yeah", "sure", "ok", "okay"}
_NEGATIVE_CONFIRMATIONS = {"no", "nope", "no thanks"}
_TRAILING_CONFIRM_PUNCT_RE = re.compile(r"[.,!?]+$")
_COMPOUND_DIRECTIVE_PROMPT = (
    "Multiple directives are not supported in one input.\nSubmit each directive separately."
)
_CLEAR_PREMISE = "clear premise"
_RESET_POLICIES = "reset policies"
_CLEAR_STATE = "clear state"
_REMOVE_POLICY_BASE = "remove policy"
_CHANGE_PREMISE_PREFIX = "change premise "
_CHANGE_PREMISE_BASE = "change premise to"
_SET_PREMISE_BASE = "set premise"
_USE_PREFIX = "use "
_PROHIBIT_BASE = "prohibit"
_PROHIBIT_PREFIX = "prohibit "
_CANONICAL_DIRECTIVE_STARTS: tuple[tuple[str, bool], ...] = (
    (_CHANGE_PREMISE_BASE, True),
    (_SET_PREMISE_BASE, True),
    (_REMOVE_POLICY_BASE, True),
    (_RESET_POLICIES, False),
    (_CLEAR_PREMISE, False),
    (_CLEAR_STATE, False),
    (_PROHIBIT_BASE, True),
    ("use", True),
)


def create_engine(state: State | None = None) -> "Engine":
    return Engine(state=state)


def get_premise_value(state: State) -> str | None:
    return state[STATE_PREMISE]


def get_policy_items(state: State, value: PolicyValue | None = None) -> list[str]:
    if value is None:
        return sorted(state[STATE_POLICIES].keys())
    return sorted(k for k, v in state[STATE_POLICIES].items() if v == value)


class Engine:
    def __init__(self, state: State | None = None) -> None:
        self._state: State
        self._replace_state(_initial_state() if state is None else _load_state_obj(state))

    @property
    def state(self) -> State:
        return deepcopy(self._state)

    def has_pending_clarification(self) -> bool:
        """Return whether a confirmation-required clarification is pending."""
        return False

    def export_json(self) -> str:
        return json.dumps(self._state, sort_keys=True, separators=(",", ":"))

    def import_json(self, payload: str) -> None:
        self._replace_state(_load_state_json(payload))

    def step(self, user_input: str) -> Decision:
        action = _parse_directive(user_input)
        if action is None:
            return _PASSTHROUGH.copy()

        clarify_decision = self._pre_mutation_clarify(action)
        if clarify_decision is not None:
            return clarify_decision

        return self._apply_action(action)

    def _replace_state(self, state: State) -> None:
        self._state = state

    def _pre_mutation_clarify(self, action: Action) -> Decision | None:
        # Single clarify path: all clarify outcomes are detected before any mutation.
        if action.kind == "compound_directive_invalid":
            return _clarify(_COMPOUND_DIRECTIVE_PROMPT)

        if action.kind in {"set_premise", "change_premise"}:
            assert action.value is not None
            if _sanitize_premise_value(action.value) == "":
                if action.kind == "set_premise":
                    return _clarify(
                        "Premise value cannot be empty.\n"
                        "Use 'set premise <value>' with a non-empty value."
                    )
                return _clarify(
                    "Premise value cannot be empty.\n"
                    "Use 'change premise to <value>' with a non-empty value."
                )

        if action.kind == "remove_policy_item":
            assert action.item is not None
            if _normalize_item(action.item) == "":
                return _clarify(
                    "Policy item cannot be empty.\n"
                    "Use 'remove policy <item>' with a non-empty value."
                )

        if action.kind == "use_item":
            assert action.item is not None
            if _normalize_item(action.item) == "":
                return _clarify(
                    "Policy item cannot be empty.\nUse 'use <item>' with a non-empty value."
                )

        if action.kind == "prohibit_item":
            assert action.item is not None
            if _normalize_item(action.item) == "":
                return _clarify(
                    "Policy item cannot be empty.\nUse 'prohibit <item>' with a non-empty value."
                )

        if action.kind == "replace_use_incomplete":
            return _clarify(
                "Replacement requires both new and old items.\n"
                "Use 'use <new item> instead of <old item>' with non-empty values."
            )

        if action.kind == "set_premise" and self._state[STATE_PREMISE] is not None:
            return _clarify("Premise already set.\nUse 'change premise to <value>' to modify it.")

        if action.kind == "change_premise" and self._state[STATE_PREMISE] is None:
            return _clarify("No premise is set.\nUse 'set premise <value>' to define one.")

        if action.kind == "use_item":
            assert action.item is not None
            item_key = _normalize_item(action.item)
            if self._state[STATE_POLICIES].get(item_key) == POLICY_PROHIBIT:
                return _clarify(
                    f'"{item_key}" is currently prohibited.\nRemove or replace it before using it.'
                )

        if action.kind == "prohibit_item":
            assert action.item is not None
            item_key = _normalize_item(action.item)
            if self._state[STATE_POLICIES].get(item_key) == POLICY_USE:
                return _clarify(
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

            old_state = self._state[STATE_POLICIES].get(old_key)
            new_state = self._state[STATE_POLICIES].get(new_key)
            if old_state == POLICY_PROHIBIT:
                return _clarify(
                    f'"{action.old_item}" is currently prohibited.\n'
                    "Submit explicit directive(s) to remove it or use a different item."
                )
            if new_state == POLICY_PROHIBIT:
                return _clarify(
                    f'"{action.new_item}" is currently prohibited.\n'
                    "Submit explicit directive(s) to remove it or use a different item."
                )
            if old_state not in {None, POLICY_USE}:
                return _clarify(
                    f'"{action.old_item}" is not currently in use.\n'
                    "Replacement requires an active 'use' policy."
                )

        return None

    def _apply_action(self, action: Action) -> Decision:
        kind = action.kind

        if kind == "set_premise":
            assert action.value is not None
            self._state[STATE_PREMISE] = _sanitize_premise_value(action.value)
            return _update_decision(self._state)

        if kind == "change_premise":
            assert action.value is not None
            self._state[STATE_PREMISE] = _sanitize_premise_value(action.value)
            return _update_decision(self._state)

        if kind == "use_item":
            assert action.item is not None
            item_key = _normalize_item(action.item)
            # Idempotent directives are updates even if state does not change.
            self._state[STATE_POLICIES][item_key] = POLICY_USE
            return _update_decision(self._state)

        if kind == "prohibit_item":
            assert action.item is not None
            item_key = _normalize_item(action.item)
            # Idempotent directives are updates even if state does not change.
            self._state[STATE_POLICIES][item_key] = POLICY_PROHIBIT
            return _update_decision(self._state)

        if kind == "replace_use":
            assert action.new_item is not None
            assert action.old_item is not None
            self._apply_replacement_explicit(action.new_item, action.old_item)
            return _update_decision(self._state)

        if kind == "remove_policy_item":
            assert action.item is not None
            item_key = _normalize_item(action.item)
            self._state[STATE_POLICIES].pop(item_key, None)
            return _update_decision(self._state)

        if kind == "clear_premise":
            self._state[STATE_PREMISE] = None
            return _update_decision(self._state)

        if kind == "reset_policies":
            self._state[STATE_POLICIES] = {}
            return _update_decision(self._state)

        self._state = _initial_state()
        return _update_decision(self._state)

    def _apply_replacement_explicit(self, new_item: str, old_item: str) -> None:
        new_key = _normalize_item(new_item)
        old_key = _normalize_item(old_item)

        if new_key == old_key:
            return

        self._state[STATE_POLICIES].pop(old_key, None)
        self._state[STATE_POLICIES][new_key] = POLICY_USE


def _parse_directive(user_input: str) -> Action | None:
    parsed = _parse_canonical_directive(user_input)
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


def _contains_compound_directive(user_input: str) -> bool:
    first_start = _match_canonical_directive_start(user_input, 0)
    if first_start is None:
        return False

    for index in range(first_start, len(user_input)):
        next_start = _match_canonical_directive_start(user_input, index)
        if next_start is not None:
            return True

    return False


def _match_canonical_directive_start(user_input: str, start: int) -> int | None:
    if start < 0 or start >= len(user_input):
        return None

    if start > 0 and user_input[start - 1].isalpha():
        return None

    for token, require_space_or_end in _CANONICAL_DIRECTIVE_STARTS:
        if _matches_directive_token(
            user_input, start, token, require_space_or_end=require_space_or_end
        ):
            return start + len(token)

    return None


def _matches_directive_token(
    user_input: str,
    start: int,
    token: str,
    *,
    require_space_or_end: bool = False,
) -> bool:
    if not user_input.startswith(token, start):
        return False

    end = start + len(token)
    if end == len(user_input):
        return True

    next_char = user_input[end]
    if require_space_or_end:
        return next_char == " "

    return not next_char.isalpha()


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


def _normalize_confirmation(text: str) -> str:
    normalized = unicode_normalize("NFKC", text)
    normalized = normalized.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = _TRAILING_CONFIRM_PUNCT_RE.sub("", normalized).strip()
    return re.sub(r"\s+", " ", normalized)


def _clarify(prompt: str) -> Decision:
    return {
        "kind": DecisionKind.CLARIFY,
        "state": None,
        "prompt_to_user": prompt,
    }


def _update_decision(state: State) -> Decision:
    return {
        "kind": DecisionKind.UPDATE,
        "state": deepcopy(state),
        "prompt_to_user": None,
    }
