"""Shared helpers for LLM-backed context compiler demos."""

import json
import re
from typing import Any

from context_compiler import Decision, State
from context_compiler.const import FOCUS_PRIMARY, POLICY_PROHIBIT, STATE_FACTS, STATE_POLICIES
from demos.llm_client import Message


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def print_user_inputs(inputs: list[str]) -> None:
    print("User inputs:")
    for index, text in enumerate(inputs, start=1):
        print(f"  {index}. {text}")
    print()


def print_decision(title: str, decision: Decision, state: State) -> None:
    print(f"Compiler decision ({title}):")
    print(canonical_json(decision))
    print("Compiled state:")
    print(canonical_json(state))
    print()


def print_messages(label: str, messages: list[Message]) -> None:
    print(f"Prompt/messages sent to LLM ({label}):")
    print(canonical_json(messages))
    print()


def print_model_output(label: str, output: str) -> None:
    print(f"{label} model output:")
    print(output)
    print()


def extract_tag_value(output: str, tag: str) -> str | None:
    pattern = rf"(?im)^\s*{re.escape(tag)}\s*:\s*([^\n]+)\s*$"
    match = re.search(pattern, output)
    if match is None:
        return None
    return match.group(1).strip()


def print_tag_comparison(tag: str, baseline_output: str, mediated_output: str) -> None:
    baseline_value = extract_tag_value(baseline_output, tag) or "MISSING"
    mediated_value = extract_tag_value(mediated_output, tag) or "MISSING"
    print(f"TAG_CHECK {tag} baseline={baseline_value} mediated={mediated_value}")
    print()


def build_compiled_system_prompt(state: State) -> str:
    focus_value = state[STATE_FACTS][FOCUS_PRIMARY]
    prohibit = state[STATE_POLICIES][POLICY_PROHIBIT]
    prohibit_text = ", ".join(prohibit) if prohibit else "(none)"
    focus_text = focus_value if focus_value is not None else "(unset)"
    return (
        "Follow authoritative compiled state exactly.\n"
        f"- facts.focus.primary: {focus_text}\n"
        f"- policies.prohibit: {prohibit_text}\n"
        "Compiled state overrides transcript drift and conflicts. "
        "Do not violate prohibited items."
    )


def build_baseline_messages(
    user_turns: list[str], *, baseline_system_prompt: str | None = None
) -> list[Message]:
    messages: list[Message] = []
    if baseline_system_prompt:
        messages.append({"role": "system", "content": baseline_system_prompt})
    messages.extend({"role": "user", "content": turn} for turn in user_turns)
    return messages


def build_mediated_messages(
    state: State, user_request: str, *, extra_system_prompt: str | None = None
) -> list[Message]:
    system_prompt = build_compiled_system_prompt(state)
    if extra_system_prompt:
        system_prompt += "\n" + extra_system_prompt
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_request},
    ]
