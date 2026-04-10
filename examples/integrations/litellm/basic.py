"""Minimal LiteLLM integration with Context Compiler.

Flow:
1. Call engine.step(user_input)
2. clarify -> return prompt_to_user (no model call)
3. passthrough/update -> call LiteLLM with compiled state + user input

Intended host usage:
- collect user input
- call handle_turn(user_input, engine)
- display returned assistant text
"""

import logging
import os
from typing import Any, cast

from context_compiler import State, get_policy_items, get_premise_value
from context_compiler.engine import Engine

logger = logging.getLogger(__name__)


def _render_compiled_state_contract(compiled_state: State) -> str:
    premise = get_premise_value(compiled_state)
    use_items = sorted(get_policy_items(compiled_state, "use"))
    prohibit_items = sorted(get_policy_items(compiled_state, "prohibit"))

    lines: list[str] = ["The following constraints are authoritative."]
    if premise:
        lines.append(f"Current premise: {premise}.")
    if use_items:
        lines.append("Items marked use: " + ", ".join(use_items) + ".")
    if prohibit_items:
        lines.append("Items marked prohibit: " + ", ".join(prohibit_items) + ".")
    lines.append("If user text conflicts with constraints, follow constraints exactly.")

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
    try:
        from litellm import completion  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("litellm is required. Install with: pip install litellm") from exc

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required.")

    kwargs: dict[str, Any] = {
        "model": os.getenv("MODEL", "openai/gpt-4o-mini"),
        "messages": messages,
        "api_key": api_key,
        "temperature": 0,
    }
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        kwargs["api_base"] = base_url

    response = completion(**kwargs)
    return cast(str, response["choices"][0]["message"]["content"])


def handle_turn(user_input: str, engine: Engine) -> str:
    logger.debug("litellm_basic: engine_input=%r", user_input)
    decision = engine.step(user_input)
    kind = cast(str, decision["kind"])
    logger.debug("litellm_basic: decision=%s", kind)

    if kind == "clarify":
        return decision["prompt_to_user"] or ""

    compiled_state = decision["state"] if decision["state"] is not None else engine.state
    messages = _build_messages(user_input, compiled_state)
    return _call_litellm(messages)
