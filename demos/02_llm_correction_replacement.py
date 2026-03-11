"""Demo 2: baseline output can mix stale facts after correction."""

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


if __name__ == "__main__":
    main()
