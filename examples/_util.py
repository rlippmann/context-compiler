import json
from typing import Any, Literal

from context_compiler import (
    POLICY_PROHIBIT,
    POLICY_USE,
    get_decision_state,
    get_error_prompt,
    is_error,
    is_update,
)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def print_json(obj: Any) -> None:
    print(canonical_json(obj))


def _format_policy_values(state: Any, value: Literal["use", "prohibit"]) -> str:
    items = sorted(
        item for item, policy_value in state["policies"].items() if policy_value == value
    )
    return ", ".join(items) if items else "(none)"


def print_state_summary(state: Any, label: str = "state") -> None:
    premise = state["premise"]
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

    if is_error(decision):
        print("result: error")
        prompt = get_error_prompt(decision)
        if isinstance(prompt, str) and prompt:
            print("error prompt:")
            for line in prompt.splitlines():
                print(f"- {line}")
        return

    print("result: no_directive")
