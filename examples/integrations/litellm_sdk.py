"""Minimal LiteLLM SDK integration example.

Architecture:
- Run Context Compiler first.
- If decision is clarify, do not call LiteLLM.
- Otherwise inject compiled state guidance and call LiteLLM once.
"""

import os
from typing import Any, cast

from litellm import completion  # type: ignore[import-not-found]

from context_compiler import State, create_engine, get_policy_items, get_premise_value


def _render_compiled_state_contract(compiled_state: State) -> str:
    prohibited = get_policy_items(compiled_state, "prohibit")
    premise = get_premise_value(compiled_state)

    lines: list[str] = ["The following constraints are authoritative."]
    if prohibited:
        items = ", ".join(prohibited)
        lines.append(f"Never recommend or use prohibited items: {items}.")
    if premise:
        lines.append(
            "When the answer depends on user preference/style, "
            f"treat the current premise as: {premise}."
        )
    lines.append("If the user message conflicts with these constraints, follow them exactly.")

    return "Host policy contract:\n" + "\n".join(f"- {line}" for line in lines)


def _build_messages(user_input: str, compiled_state: State) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": "You are a helpful assistant.\n"
            + _render_compiled_state_contract(compiled_state),
        },
        {"role": "user", "content": user_input},
    ]


def _call_litellm(messages: list[dict[str, str]]) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required.")

    kwargs: dict[str, Any] = {
        "model": os.getenv("MODEL", "openai/gpt-4o-mini"),
        "messages": messages,
        "temperature": 0,
        "api_key": api_key,
    }

    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        kwargs["api_base"] = base_url

    response = completion(**kwargs)
    return cast(str, response["choices"][0]["message"]["content"])


def handle_turn(user_input: str, engine: Any) -> str:
    decision = engine.step(user_input)

    if decision["kind"] == "clarify":
        return decision["prompt_to_user"] or ""

    compiled_state = decision["state"] if decision["state"] is not None else engine.state
    messages = _build_messages(user_input, compiled_state)
    return _call_litellm(messages)


def main() -> None:
    engine = create_engine()
    turns = [
        "set premise concise replies",
        "prohibit peanuts",
        "use peanuts",
        "plan dinner again",
    ]

    for turn in turns:
        print(f"User: {turn}")
        assistant_text = handle_turn(turn, engine)
        print(f"Assistant: {assistant_text}")
        print()


if __name__ == "__main__":
    main()
