"""Demo 3: explicit premise change removes stale values deterministically."""

import re

from context_compiler import create_engine
from demos.common import (
    build_baseline_messages,
    build_mediated_messages,
    extract_tag_value,
    print_decision,
    print_host_check,
    print_messages,
    print_model_output,
    print_spec_report,
    print_tag_comparison,
    print_user_inputs,
    yes_no,
)
from demos.llm_client import complete_messages

_PLAN_HEADING_RE = re.compile(
    r"^\s*(shopping list|ingredients?|steps?|instructions?|directions?|plan)\s*:\s*(.*)$",
    flags=re.IGNORECASE,
)
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+")
_NEGATION_RE = re.compile(r"\b(no|without|avoid|exclude|instead of)\b", flags=re.IGNORECASE)


def _plan_lines(output: str) -> list[str]:
    lines = output.splitlines()
    result: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        heading_match = _PLAN_HEADING_RE.match(stripped)
        if heading_match:
            in_section = True
            remainder = heading_match.group(2).strip()
            if remainder:
                result.append(remainder)
            continue

        if in_section or _LIST_ITEM_RE.match(stripped):
            result.append(stripped)
    return result


def _plan_uses_value(output: str, value: str) -> bool:
    token = value.lower()
    for line in _plan_lines(output):
        lowered = line.lower()
        if token not in lowered:
            continue
        if _NEGATION_RE.search(lowered):
            continue
        return True
    return False


def main() -> None:
    engine = create_engine()
    user_inputs = [
        "set premise vegetarian curry",
        "change premise to vegan curry",
        ("Give me a shopping list and 3-step plan. First line must be PREMISE:<value>."),
    ]
    print_user_inputs(user_inputs)

    for index, user_input in enumerate(user_inputs, start=1):
        decision = engine.step(user_input)
        print_decision(f"turn {index}", decision, engine.state)

    baseline_messages = build_baseline_messages(
        [user_inputs[0], user_inputs[1], user_inputs[2]],
        baseline_system_prompt=(
            "Be a helpful assistant. Use conversation history to infer the user's current premise."
        ),
    )
    print_messages("baseline", baseline_messages)
    baseline_output = complete_messages(baseline_messages)
    print_model_output("Baseline", baseline_output)

    mediated_messages = build_mediated_messages(engine.state, user_inputs[2])
    print_messages("compiler-mediated", mediated_messages)
    mediated_output = complete_messages(mediated_messages)
    print_model_output("Compiler-mediated", mediated_output)
    print_tag_comparison("PREMISE", baseline_output, mediated_output)

    baseline_premise = extract_tag_value(baseline_output, "PREMISE")
    mediated_premise = extract_tag_value(mediated_output, "PREMISE")
    baseline_uses_vegan = _plan_uses_value(baseline_output, "vegan")
    baseline_uses_vegetarian = _plan_uses_value(baseline_output, "vegetarian")
    mediated_uses_vegan = _plan_uses_value(mediated_output, "vegan")
    mediated_uses_vegetarian = _plan_uses_value(mediated_output, "vegetarian")
    baseline_respects = not baseline_uses_vegetarian
    mediated_respects = not mediated_uses_vegetarian
    print_host_check(
        "PLAN_VALUES",
        (
            f"vegan={yes_no(baseline_uses_vegan)}, "
            f"vegetarian={yes_no(baseline_uses_vegetarian)}, "
            f"premise_tag={baseline_premise or 'MISSING'}"
        ),
        context="baseline",
    )
    print_host_check(
        "PLAN_VALUES",
        (
            f"vegan={yes_no(mediated_uses_vegan)}, "
            f"vegetarian={yes_no(mediated_uses_vegetarian)}, "
            f"premise_tag={mediated_premise or 'MISSING'}"
        ),
        context="compiler-mediated",
    )
    print_spec_report(
        test_name="03_explicit_premise_change — stale value removed",
        baseline_pass=baseline_respects,
        compiler_pass=mediated_respects,
        expected="explicit premise change should remove the stale vegetarian value",
        actual=(
            "baseline still used stale vegetarian value; compiler-mediated used vegan value"
            if mediated_respects and baseline_uses_vegetarian
            else (
                "both baseline and compiler-mediated used vegan value"
                if baseline_respects and mediated_respects
                else (
                    "baseline and compiler-mediated both included stale vegetarian value"
                    if (not baseline_respects and not mediated_respects)
                    else "baseline used vegan value but compiler-mediated did not"
                )
            )
        ),
        passed=mediated_respects,
        result_pass="explicit premise change produced current authoritative value",
        result_fail="explicit premise change did not produce current authoritative value",
    )


if __name__ == "__main__":
    main()
