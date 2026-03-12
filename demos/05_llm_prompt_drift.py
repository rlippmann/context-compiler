"""Demo 5: long transcript drift vs stable compiled state."""

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
    r"^\s*(dinner plan|ingredients?|steps?|instructions?|directions?|menu|plan)\s*:\s*(.*)$",
    flags=re.IGNORECASE,
)
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+")
_NON_VEG_RE = re.compile(
    r"\b(chicken|beef|pork|bacon|ham|sausage|fish|salmon|tuna|shrimp|lamb|turkey)\b",
    flags=re.IGNORECASE,
)
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


def plan_includes_non_vegetarian_item(output: str) -> bool:
    for line in _plan_lines(output):
        if _NON_VEG_RE.search(line) is None:
            continue
        if _NEGATION_RE.search(line):
            continue
        return True
    return False


def main() -> None:
    engine = create_engine()
    user_inputs = [
        "use vegetarian curry",
        "Also I like hiking and jazz.",
        "What camera should I buy for travel?",
        "Now give me a dinner plan. First line must be DINNER_STYLE:<vegetarian|non-vegetarian>.",
    ]
    print_user_inputs(user_inputs)

    for index, user_input in enumerate(user_inputs, start=1):
        decision = engine.step(user_input)
        print_decision(f"turn {index}", decision, engine.state)

    baseline_messages = build_baseline_messages(
        [user_inputs[0], user_inputs[1], user_inputs[2], user_inputs[3]],
        baseline_system_prompt=(
            "Be a helpful assistant. Use the conversation context to provide a useful answer."
        ),
    )
    print_messages("baseline", baseline_messages)
    baseline_output = complete_messages(baseline_messages)
    print_model_output("Baseline", baseline_output)

    mediated_messages = build_mediated_messages(engine.state, user_inputs[3])
    print_messages("compiler-mediated", mediated_messages)
    mediated_output = complete_messages(mediated_messages)
    print_model_output("Compiler-mediated", mediated_output)
    print_tag_comparison("DINNER_STYLE", baseline_output, mediated_output)
    baseline_style = extract_tag_value(baseline_output, "DINNER_STYLE")
    mediated_style = extract_tag_value(mediated_output, "DINNER_STYLE")
    baseline_non_veg = plan_includes_non_vegetarian_item(baseline_output)
    mediated_non_veg = plan_includes_non_vegetarian_item(mediated_output)
    baseline_respects = not baseline_non_veg
    mediated_respects = not mediated_non_veg
    print_host_check(
        "PLAN_INCLUDES_NON_VEGETARIAN",
        f"{yes_no(baseline_non_veg)}, dinner_style_tag={baseline_style or 'MISSING'}",
        context="baseline",
    )
    print_host_check(
        "PLAN_INCLUDES_NON_VEGETARIAN",
        f"{yes_no(mediated_non_veg)}, dinner_style_tag={mediated_style or 'MISSING'}",
        context="compiler-mediated",
    )
    print_spec_report(
        test_name="05_prompt_drift — preserve key dietary constraint",
        baseline_pass=baseline_respects,
        compiler_pass=mediated_respects,
        expected=(
            "compiler-mediated should preserve the vegetarian constraint in the final dinner plan"
        ),
        actual=(
            "baseline included non-vegetarian items; compiler-mediated kept the plan vegetarian"
            if mediated_respects and baseline_non_veg
            else (
                "baseline and compiler-mediated both kept the dinner plan vegetarian"
                if not baseline_non_veg and mediated_respects
                else (
                    "baseline and compiler-mediated both included non-vegetarian items"
                    if baseline_non_veg and not mediated_respects
                    else (
                        "baseline stayed vegetarian but "
                        "compiler-mediated introduced non-vegetarian items"
                    )
                )
            )
        ),
        passed=mediated_respects,
        result_pass="vegetarian constraint preserved",
        result_fail="vegetarian constraint not preserved",
    )


if __name__ == "__main__":
    main()
