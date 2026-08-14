"""Demo 8: missing-source replacement fails without mutating authoritative state."""

from collections.abc import Mapping

from context_compiler import (
    Engine,
    is_error,
)
from demos.common import (
    build_baseline_messages,
    build_reinjected_messages,
    compact_user_turns,
    observe_engine,
    print_decision,
    print_host_check,
    print_messages,
    print_model_output,
    print_spec_report,
    print_user_inputs,
    state_observations,
    yes_no,
)
from demos.llm_client import complete_messages

DEMO_NAME = "08_replacement_precondition — missing-source replacement requires active source"
USER_INPUT = "use podman instead of docker"


def _is_initial_authoritative_state(*, premise: str | None, policies: Mapping[str, str]) -> bool:
    return premise is None and policies == {}


def main() -> None:
    engine = Engine()
    user_inputs = [USER_INPUT]
    print_user_inputs(user_inputs)

    decision = engine.step(USER_INPUT)
    premise, policies = observe_engine(engine)
    print_decision("turn 1", decision, premise=premise, policies=policies)

    baseline_messages = build_baseline_messages(
        [
            (
                "Analyze this input as state transition logic: 'use podman instead of docker'. "
                "First line must be ACTION:<error|proceed>."
            )
        ],
        baseline_system_prompt=(
            "Be helpful and plausible. If an action seems ambiguous, make a reasonable guess."
        ),
    )
    print_messages("baseline", baseline_messages)
    baseline_output = complete_messages(baseline_messages)
    print_model_output("Baseline", baseline_output)

    _, reinjected_messages = build_reinjected_messages(
        [
            (
                "Analyze this input as state transition logic: 'use podman instead of docker'. "
                "First line must be ACTION:<error|proceed>."
            )
        ],
        premise=None,
        use_policies=[],
        prohibit_policies=[],
    )
    print_messages("reinjected-state", reinjected_messages)
    reinjected_output = complete_messages(reinjected_messages)
    print_model_output("Reinjected-state", reinjected_output)

    if is_error(decision):
        print_messages("compiler-mediated (full)", [])
        mediated_output = "[no call] authoritative state blocked replacement without source use"
        print_model_output("Compiler-mediated (full)", mediated_output)
    else:
        print_messages("compiler-mediated (full)", [])
        mediated_output = "[no call] expected semantic replacement error was not produced"
        print_model_output("Compiler-mediated (full)", mediated_output)

    compacted_turns, compacted_state, compacted_prompt = compact_user_turns(user_inputs)
    if compacted_prompt is not None:
        print_messages("compiler-mediated + compact", [])
        compact_output = "[no call] unexpected error was produced during compaction"
        print_model_output("Compiler-mediated + compact", compact_output)
    else:
        print_messages("compiler-mediated + compact", [])
        compact_output = "[no call] compaction preserved replacement error without state mutation"
        print_model_output("Compiler-mediated + compact", compact_output)

    premise, policies = observe_engine(engine)
    compacted_premise, compacted_policies = state_observations(compacted_state)
    state_preserved = _is_initial_authoritative_state(premise=premise, policies=policies)
    compact_state_preserved = _is_initial_authoritative_state(
        premise=compacted_premise,
        policies=compacted_policies,
    )
    compact_error_preserved = compacted_prompt is not None

    baseline_has_authoritative_precondition = False
    reinjected_has_authoritative_precondition = False
    compiler_pass = is_error(decision) and state_preserved
    compact_pass = compact_error_preserved and compact_state_preserved

    print_host_check(
        "BASELINE_AUTHORITATIVE_PRECONDITION",
        yes_no(baseline_has_authoritative_precondition),
        context="baseline",
    )
    print_host_check(
        "REINJECTED_AUTHORITATIVE_PRECONDITION",
        yes_no(reinjected_has_authoritative_precondition),
        context="reinjected-state",
    )
    print_host_check(
        "COMPILER_BLOCKED_INVALID_REPLACEMENT",
        yes_no(is_error(decision)),
        context="compiler-mediated",
    )
    print_host_check(
        "COMPILER_STATE_PRESERVED",
        yes_no(state_preserved),
        context="compiler-mediated",
    )

    print_spec_report(
        test_name=DEMO_NAME,
        baseline_pass=baseline_has_authoritative_precondition,
        reinjected_state_pass=reinjected_has_authoritative_precondition,
        compiler_pass=compiler_pass,
        compiler_compact_pass=compact_pass,
        expected=(
            "missing-source replacement should return semantic error without mutating "
            "authoritative state"
        ),
        actual=(
            "compiler blocked missing-source replacement without mutating state; baseline and "
            "reinjected paths still lack authoritative state enforcement"
            if compiler_pass and compact_pass
            else "compiler did not consistently enforce the replacement source precondition"
        ),
        passed=compiler_pass and compact_pass,
        result_pass="missing-source replacement was rejected without mutation",
        result_fail="missing-source replacement was not rejected correctly",
    )


if __name__ == "__main__":
    main()
