import json
from typing import Any, Literal

from context_compiler import (
    POLICY_PROHIBIT,
    POLICY_USE,
    get_clarify_prompt,
    get_decision_state,
    get_policy_items,
    get_premise_value,
    is_clarify,
    is_update,
)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def print_json(obj: Any) -> None:
    print(canonical_json(obj))


def _format_policy_values(state: Any, value: Literal["use", "prohibit"]) -> str:
    items = get_policy_items(state, value)
    return ", ".join(items) if items else "(none)"


def print_state_summary(state: Any, label: str = "state") -> None:
    premise = get_premise_value(state)
    premise_text = premise if premise is not None else "(none)"

    print(f"{label}:")
    print(f"- premise: {premise_text}")
    print(f"- use policies: {_format_policy_values(state, POLICY_USE)}")
    print(f"- prohibit policies: {_format_policy_values(state, POLICY_PROHIBIT)}")


def print_decision_summary(decision: Any) -> None:
    if is_update(decision):
        print("result: updated")
        state = get_decision_state(decision)
        assert isinstance(state, dict)
        print_state_summary(state, "compiled state")
        return

    if is_clarify(decision):
        print("result: clarify")
        prompt = get_clarify_prompt(decision)
        if isinstance(prompt, str) and prompt:
            print("clarify prompt:")
            for line in prompt.splitlines():
                print(f"- {line}")
        return

    print("result: passthrough")


def print_replay_result_summary(result: Any) -> None:
    kind = result.get("kind")
    if kind == "state":
        print("result: state")
        state = result.get("state")
        assert isinstance(state, dict)
        print_state_summary(state, "compiled state")
        return

    if kind == "confirm":
        print("result: confirm")
        prompt = result.get("prompt_to_user")
        if isinstance(prompt, str) and prompt:
            print("confirm prompt:")
            for line in prompt.splitlines():
                print(f"- {line}")
