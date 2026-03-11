"""Demo 1: baseline prompt can drift from persistent constraints."""

import re

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


def host_violates_prohibit(output: str) -> bool:
    return re.search(r"\bpeanuts?\b", output, flags=re.IGNORECASE) is not None


def main() -> None:
    engine = create_engine()
    user_inputs = [
        "don't use peanuts",
        (
            "Suggest a peanut curry recipe with ingredients and steps. "
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
    baseline_violation = host_violates_prohibit(baseline_output)
    print(f"HOST_CHECK VIOLATES_PROHIBIT: {'yes' if baseline_violation else 'no'} (baseline)")
    print()

    mediated_messages = build_mediated_messages(
        engine.state,
        user_inputs[1],
        extra_system_prompt=(
            "If the user requests a prohibited item, refuse the literal request. "
            "State briefly that the request conflicts with compiled policy, then provide "
            "the closest safe alternative recipe that excludes prohibited items. "
            "Do not include prohibited item tokens in the recipe output."
        ),
    )
    print_messages("compiler-mediated", mediated_messages)
    mediated_output = complete_messages(mediated_messages)
    print_model_output("Compiler-mediated", mediated_output)
    mediated_violation = host_violates_prohibit(mediated_output)
    print(
        f"HOST_CHECK VIOLATES_PROHIBIT: {'yes' if mediated_violation else 'no'} (compiler-mediated)"
    )
    print()
    print_tag_comparison("VIOLATES_PROHIBIT", baseline_output, mediated_output)


if __name__ == "__main__":
    main()
