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


@dataclass(frozen=True)
class Action:
    kind: Literal[
        "set_premise",
        "change_premise",
        "use_item",
        "prohibit_item",
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
class PendingReplacement:
    kind: Literal["use_only", "replace_use"]
    new_item: str
    old_item: str | None = None


_PASSTHROUGH: Decision = {
    "kind": DecisionKind.PASSTHROUGH,
    "state": None,
    "prompt_to_user": None,
}

_AFFIRMATIVE_CONFIRMATIONS = {"yes", "yes please", "yep", "yeah", "sure", "ok", "okay"}
_NEGATIVE_CONFIRMATIONS = {"no", "nope", "no thanks"}
_TRAILING_CONFIRM_PUNCT_RE = re.compile(r"[.,!?]+$")


def create_engine(state: State | None = None) -> "Engine":
    return Engine(state=state)


def compile_transcript(messages: list[dict[str, object]]) -> ApplyResult:
    engine = create_engine()
    return engine.apply_transcript(messages)


def get_premise_value(state: State) -> str | None:
    return state[STATE_PREMISE]


def get_policy_items(state: State, value: PolicyValue | None = None) -> list[str]:
    if value is None:
        return sorted(state[STATE_POLICIES].keys())
    return sorted(k for k, v in state[STATE_POLICIES].items() if v == value)


class Engine:
    def __init__(self, state: State | None = None) -> None:
        self._state: State
        self._pending_replacement: PendingReplacement | None = None
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
        if self._pending_replacement is not None:
            return self._resolve_or_reprompt_pending(user_input)

        action = _parse_directive(user_input)
        if action is None:
            return _PASSTHROUGH.copy()

        clarify_decision = self._pre_mutation_clarify(action)
        if clarify_decision is not None:
            return clarify_decision

        return self._apply_action(action)

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
        self._pending_replacement = None
        self._pending_prompt = None

    def _resolve_or_reprompt_pending(self, user_input: str) -> Decision:
        assert self._pending_replacement is not None
        normalized = _normalize_confirmation(user_input)

        if normalized in _AFFIRMATIVE_CONFIRMATIONS:
            pending = self._pending_replacement
            self._pending_replacement = None
            self._pending_prompt = None
            if pending.kind == "use_only":
                new_key = _normalize_item(pending.new_item)
                self._state[STATE_POLICIES][new_key] = POLICY_USE
            else:
                assert pending.old_item is not None
                self._apply_replacement_explicit(pending.new_item, pending.old_item)
            return _update_decision(self._state)

        if normalized in _NEGATIVE_CONFIRMATIONS:
            self._pending_replacement = None
            self._pending_prompt = None
            return _update_decision(self._state)

        assert self._pending_prompt is not None
        return _clarify(self._pending_prompt)

    def _pre_mutation_clarify(self, action: Action) -> Decision | None:
        # Single clarify path: all clarify outcomes are detected before any mutation.
        if action.kind in {"set_premise", "change_premise"}:
            assert action.value is not None
            if _sanitize_premise_value(action.value) == "":
                if action.kind == "set_premise":
                    return _clarify(
                        "Premise value cannot be empty.\n"
                        "Use 'set premise ...' with a non-empty value."
                    )
                return _clarify(
                    "Premise value cannot be empty.\n"
                    "Use 'change premise to ...' with a non-empty value."
                )

        if action.kind == "set_premise" and self._state[STATE_PREMISE] is not None:
            return _clarify(
                "Premise already exists.\n"
                "Use 'change premise to ...' to replace it.\n"
                "Premise is a single slot.\n"
                "To keep multiple ideas, rewrite them as one premise value."
            )

        if action.kind == "change_premise" and self._state[STATE_PREMISE] is None:
            return _clarify("No premise exists yet. Use 'set premise ...' first.")

        if action.kind == "use_item":
            assert action.item is not None
            item_key = _normalize_item(action.item)
            if self._state[STATE_POLICIES].get(item_key) == POLICY_PROHIBIT:
                return _clarify(
                    f"'{item_key}' is already prohibited.\n"
                    "Only one policy per item is allowed.\n"
                    "Use 'reset policies' to change it."
                )

        if action.kind == "prohibit_item":
            assert action.item is not None
            item_key = _normalize_item(action.item)
            if self._state[STATE_POLICIES].get(item_key) == POLICY_USE:
                return _clarify(
                    f"'{item_key}' is already in use.\n"
                    "Only one policy per item is allowed.\n"
                    "Use 'reset policies' to change it."
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
            if old_key not in self._state[STATE_POLICIES]:
                prompt_lines = [
                    f'No exact policy found for "{action.old_item}".',
                    "Replacement requires an exact policy match.",
                ]
                diagnostic_hints = _diagnostic_policy_contains_hints(
                    self._state[STATE_POLICIES], action.old_item
                )
                if diagnostic_hints:
                    prompt_lines.append(
                        f"Existing policies containing that text: {diagnostic_hints}."
                    )
                    prompt_lines.append(
                        f'Confirm to use "{action.new_item}" and keep {diagnostic_hints}?'
                    )
                else:
                    prompt_lines.append(
                        f'Confirm to use "{action.new_item}" and keep existing policies?'
                    )
                prompt = "\n".join(prompt_lines)
                self._pending_replacement = PendingReplacement(
                    kind="use_only",
                    new_item=action.new_item,
                )
                self._pending_prompt = prompt
                return _clarify(prompt)
            if old_state == POLICY_PROHIBIT:
                prompt = (
                    f'"{action.old_item}" is currently prohibited. '
                    f'Did you mean to remove it and use "{action.new_item}" instead?'
                )
                self._pending_replacement = PendingReplacement(
                    kind="replace_use",
                    new_item=action.new_item,
                    old_item=action.old_item,
                )
                self._pending_prompt = prompt
                return _clarify(prompt)
            if new_state == POLICY_PROHIBIT:
                prompt = (
                    f'"{action.new_item}" is currently prohibited. '
                    f'Did you mean to remove "{action.old_item}" and use '
                    f'"{action.new_item}" instead?'
                )
                self._pending_replacement = PendingReplacement(
                    kind="replace_use",
                    new_item=action.new_item,
                    old_item=action.old_item,
                )
                self._pending_prompt = prompt
                return _clarify(prompt)
            if old_state != POLICY_USE:
                return _clarify(
                    f"'{action.old_item}' is not a use policy.\n"
                    "Replacement requires an existing use policy.\n"
                    "Use 'reset policies' to change it."
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
    if user_input == "clear premise":
        return Action(kind="clear_premise")
    if user_input == "reset policies":
        return Action(kind="reset_policies")
    if user_input == "clear state":
        return Action(kind="clear_state")

    set_base = "set premise"
    if user_input == set_base:
        return Action(kind="set_premise", value="")
    set_prefix = f"{set_base} "
    if user_input.startswith(set_prefix):
        value = user_input[len(set_prefix) :]
        return Action(kind="set_premise", value=value)

    change_base = "change premise to"
    if user_input == change_base:
        return Action(kind="change_premise", value="")
    change_prefix = f"{change_base} "
    if user_input.startswith(change_prefix):
        value = user_input[len(change_prefix) :]
        return Action(kind="change_premise", value=value)

    use_prefix = "use "
    if user_input.startswith(use_prefix):
        payload = user_input[len(use_prefix) :]
        left, sep, right = payload.partition(" instead of ")
        if sep:
            if left != "" and right != "":
                return Action(kind="replace_use", new_item=left, old_item=right)
            return None
        if payload != "":
            return Action(kind="use_item", item=payload)
        return None

    prohibit_prefix = "prohibit "
    if user_input.startswith(prohibit_prefix):
        item = user_input[len(prohibit_prefix) :]
        if item != "":
            return Action(kind="prohibit_item", item=item)

    return None


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
        normalized_policies[_normalize_item(key)] = value

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


def _diagnostic_policy_contains_hints(policies: dict[str, PolicyValue], raw_item: str) -> str:
    probe = _normalize_item(raw_item)
    if probe == "":
        return ""
    matches = sorted(key for key in policies if probe in key)
    if not matches:
        return ""
    return ", ".join(f'"{key}"' for key in matches)


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
