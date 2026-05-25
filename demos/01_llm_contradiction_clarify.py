"""Demo 1: compiler blocks contradictory directives before model call."""

from context_compiler import create_engine
from demos.common import (
    build_baseline_messages,
    build_mediated_messages_from_transcript,
    build_reinjected_messages,
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


def main() -> None:
    engine = create_engine()
    user_inputs = ["prohibit peanuts", "use peanuts"]
    print_user_inputs(user_inputs)

    first = engine.step(user_inputs[0])
    print_decision("turn 1", first, engine.state)
    second = engine.step(user_inputs[1])
    print_decision("turn 2", second, engine.state)

    baseline_messages = build_baseline_messages(
        [
            (
                "Interpret these directives and continue anyway: "
                "prohibit peanuts, then use peanuts. "
                "First line must be ACTION:<clarify|proceed>."
            )
        ],
        baseline_system_prompt=(
            "Be a helpful assistant. If a request is unclear, make a reasonable "
            "interpretation and answer."
        ),
    )
    print_messages("baseline", baseline_messages)
    baseline_output = complete_messages(baseline_messages)
    print_model_output("Baseline", baseline_output)

    _, reinjected_messages = build_reinjected_messages(
        [
            (
                "Interpret these directives and continue anyway: "
                "prohibit peanuts, then use peanuts. "
                "First line must be ACTION:<clarify|proceed>."
            )
        ],
        premise=None,
        use_policies=["peanuts"],
        prohibit_policies=["peanuts"],
    )
    print_messages("reinjected-state", reinjected_messages)
    reinjected_output = complete_messages(reinjected_messages)
    print_model_output("Reinjected-state", reinjected_output)

    if second["kind"] == "clarify":
        print_messages("compiler-mediated (full)", [])
        mediated_output = (
            f"[no call] clarification required: {second['prompt_to_user']}\nACTION:clarify"
        )
        print_model_output("Compiler-mediated (full)", mediated_output)
    else:
        mediated_messages = build_mediated_messages_from_transcript(engine.state, user_inputs)
        print_messages("compiler-mediated (full)", mediated_messages)
        mediated_output = complete_messages(mediated_messages)
        print_model_output("Compiler-mediated (full)", mediated_output)

    compacted_turns, compacted_state, compacted_prompt = compact_user_turns(user_inputs)
    if compacted_prompt is not None:
        print_messages("compiler-mediated + compact", [])
        compact_output = f"[no call] clarification required: {compacted_prompt}\nACTION:clarify"
        print_model_output("Compiler-mediated + compact", compact_output)
    else:
        compact_messages = build_mediated_messages_from_transcript(compacted_state, compacted_turns)
        print_messages("compiler-mediated + compact", compact_messages)
        compact_output = complete_messages(compact_messages)
        print_model_output("Compiler-mediated + compact", compact_output)

    print_tag_comparison("ACTION", baseline_output, mediated_output)
    baseline_action = extract_tag_value(baseline_output, "ACTION")
    reinjected_action = extract_tag_value(reinjected_output, "ACTION")
    compact_action = extract_tag_value(compact_output, "ACTION")
    baseline_respects = baseline_action is not None and baseline_action.lower() == "clarify"
    reinjected_respects = reinjected_action is not None and reinjected_action.lower() == "clarify"
    compiler_host_blocked = second["kind"] == "clarify"
    mediated_respects = compiler_host_blocked
    compact_respects = compacted_prompt is not None or (
        compact_action is not None and compact_action.lower() == "clarify"
    )
    print_host_check(
        "ACTION_CLARIFY",
        yes_no(reinjected_respects),
        context="reinjected-state",
    )
    print_host_check(
        "COMPILER_BLOCKED_LLM",
        yes_no(compiler_host_blocked),
        context="compiler-mediated (full)",
    )
    print_host_check(
        "COMPACT_BLOCKED_LLM",
        yes_no(compacted_prompt is not None),
        context="compiler-mediated + compact",
    )
    print_spec_report(
        test_name="01_contradiction_block — host clarification gate",
        baseline_pass=baseline_respects,
        reinjected_state_pass=reinjected_respects,
        compiler_pass=mediated_respects,
        compiler_compact_pass=compact_respects,
        expected="host should block LLM call on contradictory directive until clarification",
        actual=(
            "baseline proceeded instead of clarifying; "
            "both compiler-mediated paths blocked the LLM call"
            if mediated_respects and compact_respects and not baseline_respects
            else (
                "baseline also signaled clarification; "
                "both compiler-mediated paths blocked the LLM call"
                if baseline_respects and mediated_respects and compact_respects
                else "at least one compiler-mediated path did not block the LLM call as expected"
            )
        ),
        passed=mediated_respects and compact_respects,
        result_pass="contradictory directive blocked until clarification",
        result_fail="contradictory directive not blocked until clarification",
    )


if __name__ == "__main__":
    main()
