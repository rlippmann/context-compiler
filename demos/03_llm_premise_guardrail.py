"""Demo 3: explicit premise change removes stale values deterministically."""

import re

from context_compiler import create_engine
from demos.common import (
    build_baseline_messages,
    build_mediated_messages_from_transcript,
    compact_user_turns,
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

    mediated_messages = build_mediated_messages_from_transcript(engine.state, user_inputs)
    print_messages("compiler-mediated (full)", mediated_messages)
    mediated_output = complete_messages(mediated_messages)
    print_model_output("Compiler-mediated (full)", mediated_output)

    compacted_turns, compacted_state, compacted_prompt = compact_user_turns(user_inputs)
    if compacted_prompt is not None:
        print_messages("compiler-mediated + compact", [])
        compact_output = f"[no call] clarification required: {compacted_prompt}"
        print_model_output("Compiler-mediated + compact", compact_output)
    else:
        compact_messages = build_mediated_messages_from_transcript(compacted_state, compacted_turns)
        print_messages("compiler-mediated + compact", compact_messages)
        compact_output = complete_messages(compact_messages)
        print_model_output("Compiler-mediated + compact", compact_output)

    print_tag_comparison("PREMISE", baseline_output, mediated_output)

    baseline_premise = extract_tag_value(baseline_output, "PREMISE")
    mediated_premise = extract_tag_value(mediated_output, "PREMISE")
    compact_premise = extract_tag_value(compact_output, "PREMISE")
    baseline_uses_vegan = _plan_uses_value(baseline_output, "vegan")
    baseline_uses_vegetarian = _plan_uses_value(baseline_output, "vegetarian")
    mediated_uses_vegan = _plan_uses_value(mediated_output, "vegan")
    mediated_uses_vegetarian = _plan_uses_value(mediated_output, "vegetarian")
    compact_uses_vegan = _plan_uses_value(compact_output, "vegan")
    compact_uses_vegetarian = _plan_uses_value(compact_output, "vegetarian")
    baseline_respects = not baseline_uses_vegetarian
    mediated_respects = not mediated_uses_vegetarian
    compact_respects = compacted_prompt is None and not compact_uses_vegetarian
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
    print_host_check(
        "PLAN_VALUES",
        (
            f"vegan={yes_no(compact_uses_vegan)}, "
            f"vegetarian={yes_no(compact_uses_vegetarian)}, "
            f"premise_tag={compact_premise or 'MISSING'}"
        ),
        context="compiler-mediated + compact",
    )
    print_spec_report(
        test_name="03_explicit_premise_change — stale value removed",
        baseline_pass=baseline_respects,
        compiler_pass=mediated_respects,
        compiler_compact_pass=compact_respects,
        expected="explicit premise change should remove the stale vegetarian value",
        actual=(
            "baseline still used stale vegetarian value; "
            "both compiler-mediated paths used vegan value"
            if mediated_respects and compact_respects and baseline_uses_vegetarian
            else (
                "all three paths used vegan value"
                if baseline_respects and mediated_respects and compact_respects
                else (
                    "at least one compiler-mediated path included stale vegetarian value"
                    if (not mediated_respects or not compact_respects)
                    else (
                        "baseline already used vegan value; a compiler-mediated path "
                        "still included stale vegetarian content"
                    )
                )
            )
        ),
        passed=mediated_respects and compact_respects,
        result_pass="explicit premise change produced current authoritative value",
        result_fail="explicit premise change did not produce current authoritative value",
    )


if __name__ == "__main__":
    main()
