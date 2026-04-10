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
from collections.abc import Callable, Mapping, Sequence
from importlib import import_module
from typing import TypedDict, cast

from context_compiler import State, get_policy_items, get_premise_value
from context_compiler.engine import Engine

logger = logging.getLogger(__name__)


class _LiteLLMCallKwargs(TypedDict, total=False):
    model: str
    messages: list[dict[str, str]]
    api_key: str
    temperature: float
    api_base: str


def _extract_response_content(response: object) -> str | None:
    if isinstance(response, Mapping):
        choices = response.get("choices")
        if isinstance(choices, Sequence) and choices:
            first = choices[0]
            if isinstance(first, Mapping):
                message = first.get("message")
                if isinstance(message, Mapping):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content

    choices_attr = getattr(response, "choices", None)
    if isinstance(choices_attr, Sequence) and choices_attr:
        first = choices_attr[0]
        message_attr = getattr(first, "message", None)
        content_attr = getattr(message_attr, "content", None)
        if isinstance(content_attr, str):
            return content_attr

    return None


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
        litellm_module = import_module("litellm")
    except ModuleNotFoundError as exc:
        raise RuntimeError("litellm is required. Install with: pip install litellm") from exc
    completion_fn = cast(Callable[..., object], litellm_module.completion)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required.")

    kwargs: _LiteLLMCallKwargs = {
        "model": os.getenv("MODEL", "openai/gpt-4o-mini"),
        "messages": messages,
        "api_key": api_key,
        "temperature": 0,
    }
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        kwargs["api_base"] = base_url

    response = completion_fn(**kwargs)
    content = _extract_response_content(response)
    if content is None:
        raise RuntimeError("LiteLLM response missing choices[0].message.content")
    return content


def handle_turn(user_input: str, engine: Engine) -> str:
    logger.debug("litellm_basic: engine_input=%s", f"user_input len={len(user_input)}")
    decision = engine.step(user_input)
    kind = cast(str, decision["kind"])
    logger.debug("litellm_basic: decision=%s", kind)

    if kind == "clarify":
        return decision["prompt_to_user"] or ""

    compiled_state = decision["state"] if decision["state"] is not None else engine.state
    messages = _build_messages(user_input, compiled_state)
    return _call_litellm(messages)
