"""Minimal LiteLLM response_format selection from authoritative state.

Flow:
Context Compiler state -> host response_format decision -> LiteLLM model call.

This example keeps model execution optional so tests can validate behavior
without a live provider.
"""

import os
from collections.abc import Callable, Mapping
from importlib import import_module
from typing import Any, TypedDict, cast

from context_compiler import (
    POLICY_PROHIBIT,
    POLICY_USE,
    State,
    create_engine,
    get_clarify_prompt,
    get_decision_state,
    get_policy_items,
    is_clarify,
)
from context_compiler.engine import Engine

try:
    from host_support import print_startup_config, resolve_provider_config
except ImportError:
    from host_support.provider_mode import print_startup_config, resolve_provider_config

COMPACT_SUMMARY_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "compact_summary",
        "schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "A compact summary of the answer.",
                }
            },
            "required": ["summary"],
            "additionalProperties": False,
        },
    },
}

ACTION_PLAN_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "action_plan",
        "schema": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered next steps for the user.",
                }
            },
            "required": ["steps"],
            "additionalProperties": False,
        },
    },
}

_RESPONSE_FORMAT_BY_ITEM: dict[str, dict[str, Any]] = {
    "compact_summary": COMPACT_SUMMARY_RESPONSE_FORMAT,
    "action_plan": ACTION_PLAN_RESPONSE_FORMAT,
}


class TurnPlan(TypedDict):
    decision_kind: str
    clarify_prompt: str | None
    selected_response_format_item: str | None
    response_format: dict[str, Any] | None


class _LiteLLMCallKwargs(TypedDict, total=False):
    model: str
    messages: list[dict[str, str]]
    temperature: float
    api_base: str
    api_key: str
    response_format: dict[str, Any]


def select_litellm_response_format(state: State) -> tuple[str | None, dict[str, Any] | None]:
    """Return (policy_item, response_format) or (None, None) when no safe match exists."""

    use_items = set(get_policy_items(state, POLICY_USE))
    prohibit_items = set(get_policy_items(state, POLICY_PROHIBIT))

    for item, response_format in _RESPONSE_FORMAT_BY_ITEM.items():
        if item in use_items and item not in prohibit_items:
            return item, response_format

    return None, None


def plan_turn(user_input: str, engine: Engine) -> TurnPlan:
    """Run compiler step and decide whether to request LiteLLM structured output."""

    decision = engine.step(user_input)
    if is_clarify(decision):
        return {
            "decision_kind": "clarify",
            "clarify_prompt": get_clarify_prompt(decision),
            "selected_response_format_item": None,
            "response_format": None,
        }

    decision_state = get_decision_state(decision)
    compiled_state = decision_state if decision_state is not None else engine.state
    selected_item, response_format = select_litellm_response_format(compiled_state)

    return {
        "decision_kind": str(decision["kind"]),
        "clarify_prompt": None,
        "selected_response_format_item": selected_item,
        "response_format": response_format,
    }


def _get_litellm_completion() -> Callable[..., object]:
    litellm_module = import_module("litellm")
    return cast(Callable[..., object], litellm_module.completion)


def _extract_response_content(response: object) -> str | None:
    if isinstance(response, Mapping):
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, Mapping):
                message = first.get("message")
                if isinstance(message, Mapping):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content

    choices_attr = getattr(response, "choices", None)
    if isinstance(choices_attr, list) and choices_attr:
        first = choices_attr[0]
        message_attr = getattr(first, "message", None)
        content_attr = getattr(message_attr, "content", None)
        if isinstance(content_attr, str):
            return content_attr

    return None


def optional_litellm_call(
    *,
    user_input: str,
    response_format: Mapping[str, Any] | None,
) -> str:
    """Optional smoke call to LiteLLM.

    If `response_format` is provided, it is passed through unchanged.
    """

    try:
        completion = _get_litellm_completion()
    except ModuleNotFoundError as exc:
        raise RuntimeError("litellm is required. Install with: pip install litellm") from exc

    config = resolve_provider_config(default_model="openai/gpt-4o-mini")
    print_startup_config(config)

    kwargs: _LiteLLMCallKwargs = {
        "model": config.model,
        "messages": [{"role": "user", "content": user_input}],
        "temperature": 0,
        "api_base": config.base_url,
    }
    if config.api_key:
        kwargs["api_key"] = config.api_key
    if response_format is not None:
        kwargs["response_format"] = dict(response_format)

    response = completion(**kwargs)
    content = _extract_response_content(response)
    if content is None:
        raise RuntimeError("LiteLLM response missing choices[0].message.content")
    return content


def main() -> None:
    engine = create_engine()

    # Demonstration setup.
    engine.step("use compact_summary")
    engine.step("prohibit action_plan")

    plan = plan_turn("Summarize what changed in this project.", engine)
    print("decision_kind:", plan["decision_kind"])
    print("selected_response_format_item:", plan["selected_response_format_item"])
    print("response_format_selected:", plan["response_format"] is not None)

    # Optional model execution path; disabled by default.
    if os.getenv("RUN_LITELLM_SMOKE") == "1":
        response = optional_litellm_call(
            user_input="Summarize what changed in this project.",
            response_format=plan["response_format"],
        )
        print("litellm_response:", response)


if __name__ == "__main__":
    main()
