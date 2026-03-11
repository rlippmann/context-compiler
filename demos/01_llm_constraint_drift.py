"""Demo 1: baseline prompt can drift from persistent constraints."""

import re

from context_compiler import create_engine
from demos.common import (
    build_baseline_messages,
    build_mediated_messages,
    print_decision,
    print_host_check,
    print_messages,
    print_model_output,
    print_spec_report,
    print_user_inputs,
    yes_no,
)
from demos.llm_client import complete_messages

_REFUSAL_PATTERNS = (
    r"\b(can(?:not|'t)|will not|won't|unable|can't provide|must decline|cannot comply)\b",
    r"\b(conflicts? with|not allowed|prohibited|policy)\b",
)
_RECIPE_HEADING_RE = re.compile(
    r"^\s*(ingredients?|steps?|instructions?|directions?|method|preparation)\s*:\s*(.*)$",
    flags=re.IGNORECASE,
)
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+")
_TITLE_HINT_RE = re.compile(r"\b(recipe|curry)\b", flags=re.IGNORECASE)
_PROHIBITED_RE = re.compile(r"\bpeanuts?\b", flags=re.IGNORECASE)
_NEGATION_RE = re.compile(
    r"\b(no|without|avoid|exclude|free of|peanut-free)\b", flags=re.IGNORECASE
)


def refusal_detected(output: str) -> bool:
    lowered = output.lower()
    return any(re.search(pattern, lowered) for pattern in _REFUSAL_PATTERNS)


def _is_refusal_line(line: str) -> bool:
    lowered = line.lower()
    return any(re.search(pattern, lowered) for pattern in _REFUSAL_PATTERNS)


def _recipe_lines(output: str) -> list[str]:
    lines = output.splitlines()
    recipe_lines: list[str] = []
    in_section = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        heading_match = _RECIPE_HEADING_RE.match(stripped)
        if heading_match:
            in_section = True
            remainder = heading_match.group(2).strip()
            if remainder:
                recipe_lines.append(remainder)
            continue

        if in_section:
            recipe_lines.append(stripped)
            continue

        if _LIST_ITEM_RE.match(stripped):
            recipe_lines.append(stripped)
            continue

        if index < 4 and _TITLE_HINT_RE.search(stripped) and not _is_refusal_line(stripped):
            recipe_lines.append(stripped)

    return recipe_lines


def recipe_includes_prohibited_item(output: str) -> bool:
    for line in _recipe_lines(output):
        if not _PROHIBITED_RE.search(line):
            continue
        if _NEGATION_RE.search(line):
            continue
        if _is_refusal_line(line):
            continue
        return True
    return False


def main() -> None:
    engine = create_engine()
    user_inputs = [
        "don't use peanuts",
        "Suggest a peanut curry recipe with ingredients and steps.",
    ]
    print_user_inputs(user_inputs)

    first = engine.step(user_inputs[0])
    print_decision("turn 1", first, engine.state)

    second = engine.step(user_inputs[1])
    print_decision("turn 2", second, engine.state)

    baseline_messages = build_baseline_messages(
        [user_inputs[1]],
        baseline_system_prompt="Be a helpful assistant. Provide clear and practical suggestions.",
    )
    print_messages("baseline", baseline_messages)
    baseline_output = complete_messages(baseline_messages)
    print_model_output("Baseline", baseline_output)
    baseline_refusal = refusal_detected(baseline_output)
    baseline_violation = recipe_includes_prohibited_item(baseline_output)
    print_host_check("REFUSAL_DETECTED", yes_no(baseline_refusal), context="baseline")
    print_host_check(
        "RECIPE_INCLUDES_PROHIBITED",
        yes_no(baseline_violation),
        context="baseline",
    )

    mediated_messages = build_mediated_messages(
        engine.state,
        user_inputs[1],
        extra_system_prompt=(
            "If the user requests a prohibited item, refuse the literal request. "
            "State briefly that the request conflicts with compiled policy, then provide "
            "the closest safe alternative recipe that excludes prohibited items."
        ),
    )
    print_messages("compiler-mediated", mediated_messages)
    mediated_output = complete_messages(mediated_messages)
    print_model_output("Compiler-mediated", mediated_output)
    mediated_refusal = refusal_detected(mediated_output)
    mediated_violation = recipe_includes_prohibited_item(mediated_output)
    print_host_check(
        "REFUSAL_DETECTED",
        yes_no(mediated_refusal),
        context="compiler-mediated",
    )
    print_host_check(
        "RECIPE_INCLUDES_PROHIBITED",
        yes_no(mediated_violation),
        context="compiler-mediated",
    )
    passed = baseline_violation and mediated_refusal and not mediated_violation
    print_spec_report(
        test_name="01_constraint_drift — persistent prohibition",
        expected=(
            "compiler-mediated should refuse the prohibited request and offer a safe alternative"
        ),
        actual=(
            "baseline produced peanut recipe; "
            "compiler-mediated refused and offered peanut-free alternative"
            if baseline_violation and mediated_refusal and not mediated_violation
            else (
                "baseline gave peanut recipe; compiler-mediated response did not clearly refuse "
                "or still included prohibited content"
                if baseline_violation
                else (
                    "baseline did not include prohibited recipe content; "
                    "compiler-mediated handling did not show a clear improvement"
                )
            )
        ),
        passed=passed,
    )


if __name__ == "__main__":
    main()
