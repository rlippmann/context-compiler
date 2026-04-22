"""Deterministic state engine for explicit user directive handling."""

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, NotRequired, TypedDict
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


class CheckpointPendingReplacement(TypedDict):
    kind: Literal["use_only", "replace_use"]
    new_item: str
    old_item: str | None


class CheckpointPending(TypedDict):
    kind: Literal["replacement"]
    replacement: CheckpointPendingReplacement
    prompt_to_user: str


class Checkpoint(TypedDict):
    checkpoint_version: Literal[1]
    authoritative_state: State
    pending: NotRequired[CheckpointPending | None]


class DecisionKind(StrEnum):
    UPDATE = "update"
    PASSTHROUGH = "passthrough"
    CLARIFY = "clarify"


class Decision(TypedDict):
    kind: DecisionKind
    state: State | None
    prompt_to_user: str | None


class TranscriptMessage(TypedDict):
    role: str
    content: object


Transcript = list[TranscriptMessage]


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
        "set_premise_to_variant",
        "change_premise_missing_to_variant",
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
_CHECKPOINT_VERSION: Literal[1] = 1


def create_engine(state: State | None = None) -> "Engine":
    return Engine(state=state)


def compile_transcript(messages: Transcript) -> ApplyResult:
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

    def export_checkpoint(self) -> Checkpoint:
        pending: CheckpointPending | None = None
        if self._pending_replacement is not None:
            assert self._pending_prompt is not None
            pending = {
                "kind": "replacement",
                "replacement": {
                    "kind": self._pending_replacement.kind,
                    "new_item": self._pending_replacement.new_item,
                    "old_item": self._pending_replacement.old_item,
                },
                "prompt_to_user": self._pending_prompt,
            }

        # Reuse authoritative export/import path for canonicalized state payload.
        authoritative_state = _load_state_json(self.export_json())
        return {
            "checkpoint_version": _CHECKPOINT_VERSION,
            "authoritative_state": authoritative_state,
            "pending": pending,
        }

    def import_checkpoint(self, payload: Checkpoint) -> None:
        state, pending_replacement, pending_prompt = _load_checkpoint_obj(payload)
        self._replace_state(state)
        self._pending_replacement = pending_replacement
        self._pending_prompt = pending_prompt

    def export_checkpoint_json(self) -> str:
        return json.dumps(self.export_checkpoint(), sort_keys=True, separators=(",", ":"))

    def import_checkpoint_json(self, payload: str) -> None:
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON payload.") from exc

        self.import_checkpoint(raw)

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

    def apply_transcript(self, messages: Transcript) -> ApplyResult:
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
                        "Use 'set premise <value>' with a non-empty value."
                    )
                return _clarify(
                    "Premise value cannot be empty.\n"
                    "Use 'change premise to <value>' with a non-empty value."
                )

        if action.kind == "set_premise_to_variant":
            assert action.value is not None
            return _clarify(f"Did you mean 'set premise {action.value}'?")

        if action.kind == "change_premise_missing_to_variant":
            assert action.value is not None
            return _clarify(f"Did you mean 'change premise to {action.value}'?")

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
    if user_input == "clear premise":
        return Action(kind="clear_premise")
    if user_input == "reset policies":
        return Action(kind="reset_policies")
    if user_input == "clear state":
        return Action(kind="clear_state")

    remove_policy_base = "remove policy"
    if user_input == remove_policy_base:
        return Action(kind="remove_policy_item", item="")
    remove_policy_prefix = f"{remove_policy_base} "
    if user_input.startswith(remove_policy_prefix):
        return Action(kind="remove_policy_item", item=user_input[len(remove_policy_prefix) :])

    set_to_prefix = "set premise to "
    if user_input.startswith(set_to_prefix):
        value = user_input[len(set_to_prefix) :].strip()
        if value != "":
            return Action(kind="set_premise_to_variant", value=value)

    change_missing_to_prefix = "change premise "
    if (
        user_input.startswith(change_missing_to_prefix)
        and not user_input.startswith("change premise to ")
        and user_input != "change premise to"
    ):
        value = user_input[len(change_missing_to_prefix) :].strip()
        if value != "":
            return Action(kind="change_premise_missing_to_variant", value=value)

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

    if user_input == "use":
        return Action(kind="use_item", item="")

    use_prefix = "use "
    if user_input.startswith(use_prefix):
        payload = user_input[len(use_prefix) :]
        left, sep, right = payload.partition(" instead of ")
        if sep:
            if left.strip() != "" and right.strip() != "":
                return Action(kind="replace_use", new_item=left, old_item=right)
            return Action(kind="replace_use_incomplete")
        if payload.strip() == "":
            return Action(kind="use_item", item="")
        if payload.startswith("instead of ") or payload.endswith(" instead of"):
            return Action(kind="replace_use_incomplete")
        return Action(kind="use_item", item=payload)

    if user_input == "prohibit":
        return Action(kind="prohibit_item", item="")

    prohibit_prefix = "prohibit "
    if user_input.startswith(prohibit_prefix):
        item = user_input[len(prohibit_prefix) :]
        return Action(kind="prohibit_item", item=item)

    return None


def _initial_state() -> State:
    return {
        STATE_PREMISE: None,
        STATE_POLICIES: {},
        STATE_VERSION: SCHEMA_VERSION,
    }


def _iter_user_contents(messages: Transcript) -> list[str]:
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
        normalized_key = _normalize_item(key)
        if normalized_key == "":
            raise ValueError("Invalid state payload.")
        normalized_policies[normalized_key] = value

    return {
        STATE_PREMISE: None if premise is None else _sanitize_premise_value(premise),
        STATE_POLICIES: dict(sorted(normalized_policies.items())),
        STATE_VERSION: SCHEMA_VERSION,
    }


def _load_checkpoint_obj(raw: object) -> tuple[State, PendingReplacement | None, str | None]:
    if not isinstance(raw, dict):
        raise ValueError("Invalid checkpoint payload.")

    keys = set(raw.keys())
    if keys not in (
        {"checkpoint_version", "authoritative_state"},
        {"checkpoint_version", "authoritative_state", "pending"},
    ):
        raise ValueError("Invalid checkpoint payload.")

    checkpoint_version = raw["checkpoint_version"]
    if checkpoint_version != _CHECKPOINT_VERSION:
        raise ValueError(f"Unsupported checkpoint version: {checkpoint_version!r}")

    authoritative_state = _load_state_obj(raw["authoritative_state"])
    pending_replacement, pending_prompt = _load_checkpoint_pending_obj(raw.get("pending"))
    return authoritative_state, pending_replacement, pending_prompt


def _load_checkpoint_pending_obj(
    raw: object,
) -> tuple[PendingReplacement | None, str | None]:
    if raw is None:
        return None, None
    if not isinstance(raw, dict):
        raise ValueError("Invalid checkpoint payload.")
    if set(raw.keys()) != {"kind", "replacement", "prompt_to_user"}:
        raise ValueError("Invalid checkpoint payload.")
    if raw["kind"] != "replacement":
        raise ValueError("Invalid checkpoint payload.")

    prompt = raw["prompt_to_user"]
    if not isinstance(prompt, str):
        raise ValueError("Invalid checkpoint payload.")

    replacement = _load_checkpoint_replacement_obj(raw["replacement"])
    return replacement, prompt


def _load_checkpoint_replacement_obj(raw: object) -> PendingReplacement:
    if not isinstance(raw, dict):
        raise ValueError("Invalid checkpoint payload.")
    if set(raw.keys()) != {"kind", "new_item", "old_item"}:
        raise ValueError("Invalid checkpoint payload.")

    kind = raw["kind"]
    new_item = raw["new_item"]
    old_item = raw["old_item"]

    if kind not in {"use_only", "replace_use"}:
        raise ValueError("Invalid checkpoint payload.")
    if not isinstance(new_item, str):
        raise ValueError("Invalid checkpoint payload.")
    if _normalize_item(new_item) == "":
        raise ValueError("Invalid checkpoint payload.")

    if kind == "use_only":
        if old_item is not None:
            raise ValueError("Invalid checkpoint payload.")
        return PendingReplacement(kind=kind, new_item=new_item, old_item=None)

    if not isinstance(old_item, str):
        raise ValueError("Invalid checkpoint payload.")
    if _normalize_item(old_item) == "":
        raise ValueError("Invalid checkpoint payload.")
    return PendingReplacement(kind=kind, new_item=new_item, old_item=old_item)


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
