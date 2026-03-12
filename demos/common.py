"""Shared helpers for LLM-backed context compiler demos."""

import json
import os
import re
from typing import Any, TypedDict

from context_compiler import Decision, State
from context_compiler.const import FOCUS_PRIMARY, POLICY_PROHIBIT, STATE_FACTS, STATE_POLICIES
from demos.llm_client import Message

VERBOSE_ENV_VAR = "CONTEXT_COMPILER_DEMO_VERBOSE"


class DemoReport(TypedDict):
    name: str
    expected: str
    actual: str
    baseline_pass: bool
    compiler_pass: bool
    demo_pass: bool


class InfoReport(TypedDict):
    name: str
    baseline_context_length: int
    compiled_context_length: int
    context_reduction_percent: int
    baseline_prompt_length: int
    compiled_prompt_length: int
    prompt_reduction_percent: int


LAST_REPORT: DemoReport | None = None
LAST_INFO_REPORT: InfoReport | None = None


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def print_user_inputs(inputs: list[str]) -> None:
    if not is_verbose():
        return
    print("User inputs:")
    for index, text in enumerate(inputs, start=1):
        print(f"  {index}. {text}")
    print()


def print_decision(title: str, decision: Decision, state: State) -> None:
    if not is_verbose():
        return
    print(f"Compiler decision ({title}):")
    print(canonical_json(decision))
    print("Compiled state:")
    print(canonical_json(state))
    print()


def print_messages(label: str, messages: list[Message]) -> None:
    if not is_verbose():
        return
    print(f"Prompt/messages sent to LLM ({label}):")
    print(canonical_json(messages))
    print()


def print_model_output(label: str, output: str) -> None:
    if not is_verbose():
        return
    print(f"{label} output excerpt:")
    print(excerpt_lines(output))
    print()


def extract_tag_value(output: str, tag: str) -> str | None:
    pattern = rf"(?im)^\s*{re.escape(tag)}\s*:\s*([^\n]+)\s*$"
    match = re.search(pattern, output)
    if match is None:
        return None
    return match.group(1).strip()


def print_tag_comparison(tag: str, baseline_output: str, mediated_output: str) -> None:
    if not is_verbose():
        return
    baseline_value = extract_tag_value(baseline_output, tag) or "MISSING"
    mediated_value = extract_tag_value(mediated_output, tag) or "MISSING"
    print(f"TAG_CHECK {tag} baseline={baseline_value} mediated={mediated_value}")
    print()


def excerpt_lines(text: str, *, max_lines: int = 3) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + "\n[...]"


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def is_verbose() -> bool:
    return os.getenv(VERBOSE_ENV_VAR, "").lower() in {"1", "true", "yes", "on"}


def print_host_check(name: str, value: str, *, context: str) -> None:
    if not is_verbose():
        return
    print(f"HOST_CHECK {name}: {value} ({context})")


def print_spec_report(
    *,
    test_name: str,
    baseline_pass: bool,
    compiler_pass: bool,
    expected: str,
    actual: str,
    passed: bool,
    result_pass: str,
    result_fail: str,
) -> None:
    global LAST_REPORT
    LAST_REPORT = {
        "name": test_name,
        "expected": expected,
        "actual": actual,
        "baseline_pass": baseline_pass,
        "compiler_pass": compiler_pass,
        "demo_pass": passed,
    }
    print(test_name)
    print(f"baseline: {'PASS' if baseline_pass else 'FAIL'}")
    print(f"compiler: {'PASS' if compiler_pass else 'FAIL'}")
    print(f"expected: {expected}")
    print(f"actual: {actual}")
    print(f"result: {result_pass if passed else result_fail}")
    if is_verbose():
        print()


def consume_last_report() -> DemoReport | None:
    global LAST_REPORT
    value = LAST_REPORT
    LAST_REPORT = None
    return value


def print_info_report(
    *,
    name: str,
    baseline_context_length: int,
    compiled_context_length: int,
    context_reduction_percent: int,
    baseline_prompt_length: int,
    compiled_prompt_length: int,
    prompt_reduction_percent: int,
) -> None:
    global LAST_INFO_REPORT
    LAST_INFO_REPORT = {
        "name": name,
        "baseline_context_length": baseline_context_length,
        "compiled_context_length": compiled_context_length,
        "context_reduction_percent": context_reduction_percent,
        "baseline_prompt_length": baseline_prompt_length,
        "compiled_prompt_length": compiled_prompt_length,
        "prompt_reduction_percent": prompt_reduction_percent,
    }


def consume_last_info_report() -> InfoReport | None:
    global LAST_INFO_REPORT
    value = LAST_INFO_REPORT
    LAST_INFO_REPORT = None
    return value


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
