"""Shared helpers for LLM-backed context compiler demos."""

import os
import re
from typing import Literal, TypedDict

from context_compiler import Decision, State, get_policy_items, get_premise_value
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


def _policy_values_text(state: State, value: Literal["use", "prohibit"]) -> str:
    items = get_policy_items(state, value)
    return ", ".join(items) if items else "(none)"


def _print_state_summary(state: State) -> None:
    premise_value = get_premise_value(state)
    premise_text = premise_value if premise_value is not None else "(none)"
    print("compiled state:")
    print(f"- premise: {premise_text}")
    print(f"- use policies: {_policy_values_text(state, 'use')}")
    print(f"- prohibit policies: {_policy_values_text(state, 'prohibit')}")


def _print_multiline_prompt(label: str, prompt: str) -> None:
    print(f"{label}:")
    for line in prompt.splitlines():
        print(f"- {line}")


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
    if decision["kind"] == "update":
        print("result: updated")
        _print_state_summary(state)
    elif decision["kind"] == "clarify":
        print("result: clarify")
        prompt = decision["prompt_to_user"]
        if prompt:
            _print_multiline_prompt("clarify prompt", prompt)
        _print_state_summary(state)
    else:
        print("result: passthrough")
        _print_state_summary(state)
    print()


def print_messages(label: str, messages: list[Message]) -> None:
    if not is_verbose():
        return
    print(f"Prompt/messages sent to LLM ({label}):")
    if not messages:
        print("- (none)")
    for message in messages:
        role = message["role"]
        content = message["content"]
        lines = content.splitlines()
        if not lines:
            print(f"- {role}:")
            continue
        print(f"- {role}: {lines[0]}")
        for line in lines[1:]:
            print(f"  {line}")
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
    premise_value = get_premise_value(state)
    use_items = get_policy_items(state, "use")
    prohibit = get_policy_items(state, "prohibit")
    prohibit_text = ", ".join(prohibit) if prohibit else "(none)"
    use_text = ", ".join(use_items) if use_items else "(none)"
    premise_text = premise_value if premise_value is not None else "(unset)"
    return (
        "Follow authoritative compiled state exactly.\n"
        f"- premise: {premise_text}\n"
        f"- use policy items: {use_text}\n"
        f"- prohibited policy items: {prohibit_text}\n"
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
