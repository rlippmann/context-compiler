"""Demo 4: compiler state governs tool-choice constraints."""

from context_compiler import create_engine
from context_compiler.const import POLICY_PROHIBIT, STATE_POLICIES
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
        "don't use docker",
        (
            "Deploy the service. Pick one tool from docker, kubectl. "
            "First line must be TOOL:<docker|kubectl> and second line ACTION:<one-line action>."
        ),
    ]
    print_user_inputs(user_inputs)

    first = engine.step(user_inputs[0])
    print_decision("turn 1", first, engine.state)

    second = engine.step(user_inputs[1])
    print_decision("turn 2", second, engine.state)

    baseline_messages = build_baseline_messages(
        [user_inputs[1]],
        baseline_system_prompt="Recommend a practical approach using the available tools.",
    )
    print_messages("baseline", baseline_messages)
    baseline_output = complete_messages(baseline_messages)
    print_model_output("Baseline", baseline_output)

    prohibited = engine.state[STATE_POLICIES][POLICY_PROHIBIT]
    candidate_tools = ["docker", "kubectl"]
    filtered_tools = [tool for tool in candidate_tools if tool not in prohibited]
    print("Candidate tools before filtering:")
    print(", ".join(candidate_tools))
    print()
    print("Candidate tools after applying compiler denylist:")
    print(", ".join(filtered_tools) if filtered_tools else "(none)")
    print()

    mediated_messages = build_mediated_messages(
        engine.state,
        user_inputs[1],
        extra_system_prompt=(
            "Only choose tools that are not prohibited."
            + "\nCandidate tools: "
            + f"{', '.join(candidate_tools)}. "
            + f"Prohibited: {', '.join(prohibited) or '(none)'}"
        ),
    )
    print_messages("compiler-mediated", mediated_messages)
    mediated_output = complete_messages(mediated_messages)
    print_model_output("Compiler-mediated", mediated_output)
    print_tag_comparison("TOOL", baseline_output, mediated_output)


if __name__ == "__main__":
    main()
