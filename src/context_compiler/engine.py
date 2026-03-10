"""Deterministic M1 state engine for explicit user directive handling.

This module provides a small, model-independent state machine that parses
high-confidence directives and emits host decisions without invoking an LLM.
Only explicit user directives can mutate authoritative state.
"""

import re
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, TypedDict
from unicodedata import normalize as unicode_normalize

from .const import (
    FOCUS_PRIMARY,
    POLICY_PROHIBIT,
    STATE_FACTS,
    STATE_POLICIES,
    STATE_VERSION,
)

FactsState = TypedDict("FactsState", {"focus.primary": str | None})


class PoliciesState(TypedDict):
    prohibit: list[str]


class State(TypedDict):
    """Versioned authoritative state; future versions may add new fields."""

    facts: FactsState
    policies: PoliciesState
    version: Literal[1]


class DecisionKind(StrEnum):
    UPDATE = "update"
    PASSTHROUGH = "passthrough"
    CLARIFY = "clarify"


class Decision(TypedDict):
    kind: DecisionKind
    state: State | None
    prompt_to_user: str | None


@dataclass(frozen=True)
class PendingEvent:
    kind: Literal["policy_add", "policy_remove", "fact_set", "reset_policies", "clear_state"]
    values: tuple[str, ...] = ()
    fact_value: str | None = None
    requires_confirmation: bool = False


@dataclass(frozen=True)
class NegativeDirectiveRule:
    starter: str
    kind: Literal["policy_add"]
    strip_leading_use: bool


_RESET_POLICY = {"reset policies", "clear constraints"}
_CLEAR_STATE = {"clear state"}

_CORRECTION_RE = re.compile(r"^\s*(actually|i meant|correction:|no,)\s*(.*?)\s*$", re.IGNORECASE)
_POSITIVE_RE = re.compile(
    r"^\s*(?:use|set|i\s+am\s+using|i['’]m\s+using)\s+(.+?)\s*$", re.IGNORECASE
)
_ALLOW_PREFIX_RE = re.compile(r"^\s*(?:allow|you\s+can)\s+(.+?)\s*$", re.IGNORECASE)
_ALLOW_SUFFIX_RE = re.compile(r"^\s*(.+?)\s+is\s+fine\s*$", re.IGNORECASE)

_AMBIGUOUS_NEGATIVE_RE = re.compile(r"^\s*(?:don\s+use|no\s+use)\s+(.+?)\s*$", re.IGNORECASE)
_SPLIT_RE = re.compile(r",|\s+and\s+", re.IGNORECASE)

_PASSTHROUGH: Decision = {
    "kind": DecisionKind.PASSTHROUGH,
    "state": None,
    "prompt_to_user": None,
}

_NEGATIVE_DIRECTIVE_RULES: tuple[NegativeDirectiveRule, ...] = (
    NegativeDirectiveRule(starter="please don't ", kind="policy_add", strip_leading_use=True),
    NegativeDirectiveRule(starter="don't ", kind="policy_add", strip_leading_use=True),
    NegativeDirectiveRule(starter="do not ", kind="policy_add", strip_leading_use=True),
    NegativeDirectiveRule(starter="never ", kind="policy_add", strip_leading_use=True),
)


def create_engine() -> "Engine":
    """Create a new deterministic Engine instance with initial M1 state."""
    return Engine()


class Engine:
    """Deterministic state engine implementing M1 directive semantics."""

    def __init__(self) -> None:
        self._state: State = _initial_state()
        self._pending: PendingEvent | None = None
        self._pending_prompt: str | None = None
        self._last_exclusive_fact_key: str | None = None

    @property
    def state(self) -> State:
        """Return a defensive copy of the current authoritative state snapshot."""
        return deepcopy(self._state)

    def step(self, user_input: str) -> Decision:
        """Process one user input and return a deterministic Decision."""
        if self._pending is not None:
            return self._resolve_or_reprompt_pending(user_input)

        classified = self._classify(user_input)

        if isinstance(classified, dict):
            return classified

        if not classified.requires_confirmation:
            return self._apply_pending(classified)

        self._pending = classified
        self._pending_prompt = _pending_prompt(classified)
        return _clarify(self._pending_prompt)

    def _classify(self, user_input: str) -> PendingEvent | Decision:
        normalized_message = _normalize_message(user_input)

        if normalized_message in _RESET_POLICY:
            return PendingEvent(kind="reset_policies")

        if normalized_message in _CLEAR_STATE:
            return PendingEvent(kind="clear_state")

        correction = _parse_correction(user_input)
        if correction is not None:
            if self._last_exclusive_fact_key is None:
                return _clarify_no_prior_change(correction)
            if not correction.strip():
                return _clarify_missing_value()
            if _has_multiple_values(correction):
                return _clarify_single_value()
            if _invalid_exclusive_value(correction):
                return _clarify_unclear_value()
            return PendingEvent(kind="fact_set", fact_value=correction)

        policy_add = _parse_hard_negative(normalized_message)
        if policy_add is not None:
            if not policy_add:
                return _clarify("What should I prohibit?")
            return PendingEvent(kind="policy_add", values=tuple(policy_add))

        policy_remove = _parse_allow(user_input)
        if policy_remove is not None:
            if not policy_remove:
                return _clarify("What should I allow?")
            return PendingEvent(kind="policy_remove", values=tuple(policy_remove))

        positive_value = _parse_hard_positive(user_input, normalized_message)
        if positive_value is not None:
            if not positive_value.strip():
                return _clarify_missing_value()
            if _has_multiple_values(positive_value):
                return _clarify_single_value()
            if _invalid_exclusive_value(positive_value):
                return _clarify_unclear_value()
            return PendingEvent(kind="fact_set", fact_value=positive_value)

        pending = _parse_ambiguous_mutation(user_input)
        if pending is not None:
            if len(pending.values) != 1:
                return _clarify("Your directive was unclear. Please specify one item.")
            return PendingEvent(
                kind=pending.kind,
                values=pending.values,
                fact_value=pending.fact_value,
                requires_confirmation=True,
            )

        return _PASSTHROUGH.copy()

    def _resolve_or_reprompt_pending(self, user_input: str) -> Decision:
        assert self._pending is not None
        pending = self._pending
        response = _normalize_message(user_input)

        if response == "yes":
            self._pending = None
            self._pending_prompt = None
            return self._apply_pending(pending)

        if response == "no":
            self._pending = None
            self._pending_prompt = None
            return _PASSTHROUGH.copy()

        prompt = self._pending_prompt or "Please answer yes or no."
        return _clarify(f"{prompt} Please answer yes or no.")

    def _apply_pending(self, pending: PendingEvent) -> Decision:
        return self._apply_event(pending)

    def _apply_event(self, event: PendingEvent) -> Decision:
        """Apply a PendingEvent to authoritative state."""
        if event.kind == "policy_add":
            return self._add_policies(list(event.values))
        if event.kind == "policy_remove":
            return self._remove_policies(list(event.values))
        if event.kind == "fact_set":
            assert event.fact_value is not None
            return self._set_focus_primary(event.fact_value)
        if event.kind == "reset_policies":
            self._state = _initial_state()
            self._last_exclusive_fact_key = None
            return _update_decision(self._state)

        self._state = _initial_state()
        self._last_exclusive_fact_key = None
        return _update_decision(self._state)

    def _set_focus_primary(self, value: str) -> Decision:
        self._state[STATE_FACTS][FOCUS_PRIMARY] = _clean_fact_value(value)
        self._last_exclusive_fact_key = FOCUS_PRIMARY
        return _update_decision(self._state)

    def _add_policies(self, values: list[str]) -> Decision:
        existing = set(self._state[STATE_POLICIES][POLICY_PROHIBIT])
        for value in values:
            existing.add(value)
        self._state[STATE_POLICIES][POLICY_PROHIBIT] = sorted(existing)
        return _update_decision(self._state)

    def _remove_policies(self, values: list[str]) -> Decision:
        existing = set(self._state[STATE_POLICIES][POLICY_PROHIBIT])
        for value in values:
            existing.discard(value)
        self._state[STATE_POLICIES][POLICY_PROHIBIT] = sorted(existing)
        return _update_decision(self._state)


def _initial_state() -> State:
    return {
        STATE_FACTS: {FOCUS_PRIMARY: None},
        STATE_POLICIES: {POLICY_PROHIBIT: []},
        STATE_VERSION: 1,
    }


def _clarify(prompt: str) -> Decision:
    return {
        "kind": DecisionKind.CLARIFY,
        "state": None,
        "prompt_to_user": prompt,
    }


def _clarify_missing_value() -> Decision:
    return _clarify("What should I use?")


def _clarify_single_value() -> Decision:
    return _clarify("Please provide a single value to use.")


def _clarify_unclear_value() -> Decision:
    return _clarify("The value is unclear. Please provide a single value to use.")


def _clarify_no_prior_change(value: str) -> Decision:
    return _clarify(f'There\'s nothing to change from yet. Did you mean to use "{value}"?')


def _update_decision(state: State) -> Decision:
    return {
        "kind": DecisionKind.UPDATE,
        "state": deepcopy(state),
        "prompt_to_user": None,
    }


def _normalize_message(text: str) -> str:
    normalized = unicode_normalize("NFKC", text).lower().strip()
    normalized = normalized.replace("’", "'").replace("`", "'")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\bdont\b", "don't", normalized)
    return normalized


def _clean_fact_value(value: str) -> str:
    normalized = unicode_normalize("NFKC", value).strip()
    normalized = normalized.replace("’", "'").replace("`", "'")
    return re.sub(r"\s+", " ", normalized)


def _normalize_item(text: str) -> str:
    item = _normalize_message(text)
    item = re.sub(r"^(?:a|an|the)\s+", "", item)
    return item.strip()


def _split_items(text: str) -> list[str]:
    pieces = _SPLIT_RE.split(text)
    values: list[str] = []
    for piece in pieces:
        normalized = _normalize_item(piece)
        if normalized:
            values.append(normalized)
    return values


def _has_multiple_values(text: str) -> bool:
    pieces = _SPLIT_RE.split(text)
    non_empty = [piece.strip() for piece in pieces if piece.strip()]
    return len(non_empty) > 1


def _invalid_exclusive_value(text: str) -> bool:
    lowered = _normalize_message(text)
    return (
        lowered.startswith("and ")
        or lowered.startswith("or ")
        or lowered == "and"
        or lowered == "or"
    )


def _parse_correction(user_input: str) -> str | None:
    match = _CORRECTION_RE.match(user_input)
    if not match:
        return None
    return match.group(2)


def _parse_hard_negative(normalized_message: str) -> list[str] | None:
    msg = normalized_message

    for rule in _NEGATIVE_DIRECTIVE_RULES:
        if not msg.startswith(rule.starter):
            continue

        payload = msg[len(rule.starter) :].strip()
        if rule.strip_leading_use:
            payload = re.sub(r"^use\s+", "", payload, count=1)
        return _split_items(payload)

    return None


def _parse_hard_positive(user_input: str, normalized_message: str) -> str | None:
    if not (
        normalized_message.startswith("use ")
        or normalized_message.startswith("set ")
        or normalized_message.startswith("i am using ")
        or normalized_message.startswith("i'm using ")
    ):
        return None

    candidate = user_input.strip()
    if re.match(r"(?i)^please\s+", candidate):
        candidate = re.sub(r"(?i)^please\s+", "", candidate, count=1)

    match = _POSITIVE_RE.match(candidate)
    if not match:
        return None
    return match.group(1)


def _parse_allow(user_input: str) -> list[str] | None:
    match_prefix = _ALLOW_PREFIX_RE.match(user_input)
    if match_prefix:
        return _split_items(match_prefix.group(1))

    match_suffix = _ALLOW_SUFFIX_RE.match(user_input)
    if match_suffix:
        return _split_items(match_suffix.group(1))

    return None


def _parse_ambiguous_mutation(user_input: str) -> PendingEvent | None:
    match = _AMBIGUOUS_NEGATIVE_RE.match(user_input)
    if not match:
        return None

    values = _split_items(match.group(1))
    if values:
        return PendingEvent(kind="policy_add", values=tuple(values))

    return None


def _pending_prompt(pending: PendingEvent) -> str:
    if pending.kind == "policy_add" and pending.values:
        return f"Did you mean to prohibit '{pending.values[0]}'?"
    if pending.kind == "policy_remove" and pending.values:
        return f"Did you mean to allow '{pending.values[0]}'?"
    if pending.kind == "fact_set" and pending.fact_value is not None:
        return f'Did you mean to use "{pending.fact_value}"?'
    return "Your directive was unclear. Did you mean to change state?"
