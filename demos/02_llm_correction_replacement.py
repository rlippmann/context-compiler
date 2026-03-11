"""Demo 2: baseline output can mix stale facts after correction."""

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
_META_CONTEXT_RE = re.compile(
    r"\b(previous|previously|earlier|before|history|changed|correction|from|to|instead)\b",
    flags=re.IGNORECASE,
)


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


def _is_meta_line(line: str) -> bool:
    lowered = line.lower()
    # Meta/explanatory lines often mention both values in correction context.
    if "vegan" in lowered and "vegetarian" in lowered and _META_CONTEXT_RE.search(lowered):
        return True
    return bool(_META_CONTEXT_RE.search(lowered) and "focus_primary" in lowered)


def _plan_uses_value(output: str, value: str) -> bool:
    token = value.lower()
    for line in _plan_lines(output):
        lowered = line.lower()
        if token not in lowered:
            continue
        if _NEGATION_RE.search(lowered):
            continue
        if _is_meta_line(line):
            continue
        return True
    return False


def main() -> None:
    engine = create_engine()
    user_inputs = [
        "use vegetarian curry",
        "actually vegan curry",
        ("Give me a shopping list and 3-step plan. First line must be FOCUS_PRIMARY:<value>."),
    ]
    print_user_inputs(user_inputs)

    for index, user_input in enumerate(user_inputs, start=1):
        decision = engine.step(user_input)
        print_decision(f"turn {index}", decision, engine.state)

    baseline_messages = build_baseline_messages(
        [user_inputs[0], user_inputs[1], user_inputs[2]],
        baseline_system_prompt=(
            "Be a helpful assistant. Use the conversation history to understand "
            "the user's preferences."
        ),
    )
    print_messages("baseline", baseline_messages)
    baseline_output = complete_messages(baseline_messages)
    print_model_output("Baseline", baseline_output)

    mediated_messages = build_mediated_messages(engine.state, user_inputs[2])
    print_messages("compiler-mediated", mediated_messages)
    mediated_output = complete_messages(mediated_messages)
    print_model_output("Compiler-mediated", mediated_output)
    print_tag_comparison("FOCUS_PRIMARY", baseline_output, mediated_output)
    baseline_focus = extract_tag_value(baseline_output, "FOCUS_PRIMARY")
    mediated_focus = extract_tag_value(mediated_output, "FOCUS_PRIMARY")
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
            f"focus_tag={baseline_focus or 'MISSING'}"
        ),
        context="baseline",
    )
    print_host_check(
        "PLAN_VALUES",
        (
            f"vegan={yes_no(mediated_uses_vegan)}, "
            f"vegetarian={yes_no(mediated_uses_vegetarian)}, "
            f"focus_tag={mediated_focus or 'MISSING'}"
        ),
        context="compiler-mediated",
    )
    print_spec_report(
        test_name="02_correction_replacement — latest value wins",
        expected="the corrected vegan preference should determine the final plan",
        actual=(
            "baseline still used the stale vegetarian value; "
            "compiler-mediated used the corrected vegan value"
            if mediated_respects and baseline_uses_vegetarian
            else (
                "both baseline and compiler-mediated followed the corrected vegan preference"
                if baseline_respects and mediated_respects
                else (
                    "baseline and compiler-mediated both mixed stale and corrected values"
                    if (not baseline_respects and not mediated_respects)
                    else "baseline followed corrected preference but compiler-mediated did not"
                )
            )
        ),
        passed=mediated_respects,
    )


if __name__ == "__main__":
    main()
