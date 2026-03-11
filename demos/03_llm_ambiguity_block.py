"""Demo 3: compiler blocks ambiguous directives before model call."""

from context_compiler import create_engine
from demos.common import (
    build_baseline_messages,
    print_decision,
    print_messages,
    print_model_output,
    print_tag_comparison,
    print_user_inputs,
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


if __name__ == "__main__":
    main()
