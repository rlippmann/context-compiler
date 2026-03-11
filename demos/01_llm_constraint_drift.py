"""Demo 1: baseline prompt can drift from persistent constraints."""

from context_compiler import create_engine
from demos.common import (
    build_baseline_messages,
    build_mediated_messages,
    print_decision,
    print_messages,
    print_model_output,
    print_tag_comparison,
    print_user_inputs,
)
from demos.llm_client import complete_messages


def main() -> None:
    engine = create_engine()
    user_inputs = [
        "don't use peanuts",
        (
            "Suggest a curry recipe with ingredients and steps. "
            "First line must be VIOLATES_PROHIBIT:<yes|no>."
        ),
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

    mediated_messages = build_mediated_messages(engine.state, user_inputs[1])
    print_messages("compiler-mediated", mediated_messages)
    mediated_output = complete_messages(mediated_messages)
    print_model_output("Compiler-mediated", mediated_output)
    print_tag_comparison("VIOLATES_PROHIBIT", baseline_output, mediated_output)


if __name__ == "__main__":
    main()
