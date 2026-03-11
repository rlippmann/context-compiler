"""Demo 3: compiler blocks ambiguous directives before model call."""

from context_compiler import create_engine
from demos.common import (
    build_baseline_messages,
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
from demos.llm_client import Message, complete_messages


def main() -> None:
    engine = create_engine()
    user_inputs = ["no use peanuts"]
    print_user_inputs(user_inputs)

    decision = engine.step(user_inputs[0])
    print_decision("turn 1", decision, engine.state)

    baseline_messages = build_baseline_messages(
        [
            (
                "Interpret this directive and continue anyway: no use peanuts. "
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

    if decision["kind"] == "clarify":
        print_messages("compiler-mediated", [])
        mediated_output = (
            f"[no call] clarification required: {decision['prompt_to_user']}\nACTION:clarify"
        )
        print_model_output("Compiler-mediated", mediated_output)
    else:
        mediated_messages: list[Message] = [{"role": "user", "content": user_inputs[0]}]
        print_messages("compiler-mediated", mediated_messages)
        mediated_output = complete_messages(mediated_messages)
        print_model_output("Compiler-mediated", mediated_output)

    print_tag_comparison("ACTION", baseline_output, mediated_output)
    baseline_action = extract_tag_value(baseline_output, "ACTION")
    baseline_respects = baseline_action is not None and baseline_action.lower() == "clarify"
    compiler_host_blocked = decision["kind"] == "clarify"
    mediated_respects = compiler_host_blocked
    print_host_check(
        "COMPILER_BLOCKED_LLM",
        yes_no(compiler_host_blocked),
        context="compiler-mediated",
    )
    print_spec_report(
        test_name="03_ambiguity_block — host clarification gate",
        expected="host should block LLM call on ambiguous directive until clarification",
        actual=(
            "baseline answered instead of clarifying; compiler-mediated blocked the LLM call"
            if mediated_respects and not baseline_respects
            else (
                "baseline also signaled clarification; compiler-mediated blocked the LLM call"
                if baseline_respects and mediated_respects
                else "compiler-mediated did not block the LLM call as expected"
            )
        ),
        passed=mediated_respects,
    )


if __name__ == "__main__":
    main()
