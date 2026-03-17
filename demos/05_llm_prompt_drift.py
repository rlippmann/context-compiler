"""Demo 5: long transcript drift vs stable compiled state."""

import argparse
import re

import demos.llm_client as llm_client
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

_ORIGINAL_DIRECTIVE = "use vegetarian curry"
_FINAL_PROMPT = (
    "Now give me a dinner plan. First line must be DINNER_STYLE:<vegetarian|non-vegetarian>."
)
_DISTRACTOR_TOPICS = [
    "travel photography",
    "city walking routes",
    "weekend train trips",
    "mountain day hikes",
    "pour-over coffee brewing",
    "espresso dialing",
    "architecture sketching",
    "museum planning",
    "weather map reading",
    "atlas navigation",
    "independent bookstores",
    "historical nonfiction reading",
    "film photography",
    "macro photography",
    "night sky viewing",
    "rail station architecture",
    "public transit maps",
    "urban design tours",
    "coastal trail planning",
    "desert trail planning",
    "baking crust hydration",
    "pan sauce reduction",
    "knife-skill practice",
    "tea brewing",
    "city museum circuits",
]
_DISTRACTOR_PROMPT_TEMPLATES = [
    "Quick question on {topic}: which beginner book gives solid fundamentals?",
    "For {topic}, what common pitfall surprises newcomers?",
    "In {topic}, which metric helps compare two options fairly?",
    "How would you plan a one-day itinerary around {topic}?",
    "For {topic}, what gear checklist keeps things practical?",
    "In {topic}, what weather factor changes decisions the most?",
    "What map detail matters most when preparing for {topic}?",
    "For {topic}, which habit improves consistency over months?",
    "How can someone budget for {topic} without losing quality?",
    "For {topic}, what tradeoff appears between speed and accuracy?",
    "What museum exhibit style pairs well with interest in {topic}?",
    "For {topic}, which train route offers the most scenic segments?",
]


def _build_master_distractor_sequence() -> list[str]:
    sequence = [
        # Keep these first two distractors byte-identical to the original demo.
        "Also I like hiking and jazz.",
        "What camera should I buy for travel?",
    ]
    for topic in _DISTRACTOR_TOPICS:
        for template in _DISTRACTOR_PROMPT_TEMPLATES:
            sequence.append(template.format(topic=topic))
    return sequence


_MASTER_DISTRACTOR_SEQUENCE = _build_master_distractor_sequence()
if len(_MASTER_DISTRACTOR_SEQUENCE) < 240:
    raise RuntimeError("Demo 5 distractor sequence must support at least 240 turns.")


_LADDER_TURNS = [10, 30, 60, 120, 240]
_DEFAULT_TURNS = 2


_ORIGINAL_DEFAULT_TRANSCRIPT = [
    _ORIGINAL_DIRECTIVE,
    "Also I like hiking and jazz.",
    "What camera should I buy for travel?",
    _FINAL_PROMPT,
]


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


def _validate_turns(turns: int) -> None:
    max_turns = len(_MASTER_DISTRACTOR_SEQUENCE)
    if turns < 0:
        raise ValueError("turns must be at least 0.")
    if turns > max_turns:
        raise ValueError(f"turns must be <= {max_turns}.")


def build_context_turns(turns: int) -> list[str]:
    _validate_turns(turns)
    return [_ORIGINAL_DIRECTIVE, *_MASTER_DISTRACTOR_SEQUENCE[:turns]]


def build_user_inputs(turns: int) -> list[str]:
    return [*build_context_turns(turns), _FINAL_PROMPT]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    max_turns = len(_MASTER_DISTRACTOR_SEQUENCE)
    parser = argparse.ArgumentParser(
        description=(
            "Run Demo 5 with deterministic distractor distance for prompt-drift stress testing."
        )
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=_DEFAULT_TURNS,
        help=(
            "Number of distractor turns between the original directive and final prompt "
            f"(0-{max_turns}). Supports stress-test ladder points: "
            f"{', '.join(map(str, _LADDER_TURNS))}."
        ),
    )
    parser.add_argument(
        "--llm-delay",
        type=float,
        default=None,
        help="Delay between LLM calls in seconds (overrides shared default when provided).",
    )
    args = parser.parse_args(argv)
    _validate_turns(args.turns)
    return args


def _run_demo(turns: int = _DEFAULT_TURNS) -> None:
    engine = create_engine()
    user_inputs = build_user_inputs(turns)
    if turns == _DEFAULT_TURNS and user_inputs != _ORIGINAL_DEFAULT_TRANSCRIPT:
        raise RuntimeError("Demo 5 default transcript diverged from original behavior.")
    print_user_inputs(user_inputs)

    for index, user_input in enumerate(user_inputs, start=1):
        decision = engine.step(user_input)
        print_decision(f"turn {index}", decision, engine.state)

    baseline_messages = build_baseline_messages(
        user_inputs,
        baseline_system_prompt=(
            "Be a helpful assistant. Use the conversation context to provide a useful answer."
        ),
    )
    print_messages("baseline", baseline_messages)
    baseline_output = complete_messages(baseline_messages)
    print_model_output("Baseline", baseline_output)

    mediated_messages = build_mediated_messages(engine.state, user_inputs[-1])
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


def main(turns: int = _DEFAULT_TURNS, llm_delay: float | None = None) -> None:
    old_delay = llm_client.DEFAULT_LLM_DELAY_SECONDS
    if llm_delay is not None:
        llm_client.DEFAULT_LLM_DELAY_SECONDS = llm_delay if llm_delay > 0 else 0.0
    try:
        _run_demo(turns=turns)
    finally:
        if llm_delay is not None:
            llm_client.DEFAULT_LLM_DELAY_SECONDS = old_delay


if __name__ == "__main__":
    cli_args = _parse_args()
    main(turns=cli_args.turns, llm_delay=cli_args.llm_delay)
