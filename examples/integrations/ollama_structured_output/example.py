"""Minimal host-side Ollama structured-output schema selection.

Flow:
Context Compiler state -> host selection logic -> Ollama `format` JSON Schema.

This example keeps model execution optional so tests can validate behavior without Ollama.
"""

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
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

PYTHON_SCRIPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "python_script": {
            "type": "string",
            "description": "A complete Python script.",
        }
    },
    "required": ["python_script"],
    "additionalProperties": False,
}

SHELL_COMMAND_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "shell_command": {
            "type": "string",
            "description": "A single shell command.",
        }
    },
    "required": ["shell_command"],
    "additionalProperties": False,
}

# Small, explicit mapping from policy item -> Ollama `format` schema.
_SCHEMA_BY_ITEM: dict[str, dict[str, Any]] = {
    "python_script": PYTHON_SCRIPT_SCHEMA,
    "shell_command": SHELL_COMMAND_SCHEMA,
}


class TurnPlan(TypedDict):
    decision_kind: str
    clarify_prompt: str | None
    selected_schema_item: str | None
    format_schema: dict[str, Any] | None


def select_ollama_format_schema(state: State) -> tuple[str | None, dict[str, Any] | None]:
    """Return (policy_item, schema) or (None, None) when no safe match exists.

    Unknown/insufficient policy state intentionally selects no schema.
    """

    use_items = set(get_policy_items(state, POLICY_USE))
    prohibit_items = set(get_policy_items(state, POLICY_PROHIBIT))

    for item, schema in _SCHEMA_BY_ITEM.items():
        if item in use_items and item not in prohibit_items:
            return item, schema

    return None, None


def plan_turn(user_input: str, engine: Engine) -> TurnPlan:
    """Run compiler step and decide whether to request Ollama structured output."""

    decision = engine.step(user_input)
    if is_clarify(decision):
        return {
            "decision_kind": "clarify",
            "clarify_prompt": get_clarify_prompt(decision),
            "selected_schema_item": None,
            "format_schema": None,
        }

    decision_state = get_decision_state(decision)
    compiled_state = decision_state if decision_state is not None else engine.state
    selected_item, format_schema = select_ollama_format_schema(compiled_state)

    return {
        "decision_kind": str(decision["kind"]),
        "clarify_prompt": None,
        "selected_schema_item": selected_item,
        "format_schema": format_schema,
    }


def optional_ollama_call(
    *,
    user_input: str,
    model: str,
    format_schema: Mapping[str, Any] | None,
    host: str | None = None,
) -> dict[str, Any]:
    """Optional smoke call to Ollama's /api/chat.

    If `format_schema` is provided, it is passed through `format` exactly.
    """

    base_url = host or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": user_input}],
        "stream": False,
    }
    if format_schema is not None:
        payload["format"] = dict(format_schema)

    request = urllib.request.Request(
        url=f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama call failed: {exc}") from exc

    decoded = cast(object, json.loads(raw))
    if not isinstance(decoded, dict):
        raise RuntimeError("Ollama response must be a JSON object")
    return cast(dict[str, Any], decoded)


def main() -> None:
    engine = create_engine()

    # Demonstration setup.
    engine.step("use python_script")
    engine.step("prohibit shell_command")

    plan = plan_turn("Write a helper script to parse CSV files.", engine)
    print("decision_kind:", plan["decision_kind"])
    print("selected_schema_item:", plan["selected_schema_item"])
    print("format_schema_selected:", plan["format_schema"] is not None)

    # Optional model execution path; disabled by default.
    if os.getenv("RUN_OLLAMA_SMOKE") == "1":
        response = optional_ollama_call(
            user_input="Write a helper script to parse CSV files.",
            model=os.getenv("OLLAMA_MODEL", "llama3.1"),
            format_schema=plan["format_schema"],
        )
        print("ollama_response_keys:", sorted(response.keys()))


if __name__ == "__main__":
    main()
