"""Demo 8: missing-source replacement applies deterministically from authoritative state."""

from context_compiler import DECISION_UPDATE, State, create_engine
from demos.common import (
    build_baseline_messages,
    build_reinjected_messages,
    compact_user_turns,
    print_decision,
    print_host_check,
    print_messages,
    print_model_output,
    print_spec_report,
    print_user_inputs,
    yes_no,
)
from demos.llm_client import complete_messages

DEMO_NAME = "08_replacement_precondition — missing-source replacement applies deterministically"
USER_INPUT = "use podman instead of docker"


def _is_initial_authoritative_state(state: State) -> bool:
    return state == {"premise": None, "policies": {}, "version": 2}


def main() -> None:
    engine = create_engine()
    user_inputs = [USER_INPUT]
    print_user_inputs(user_inputs)

    decision = engine.step(USER_INPUT)
    print_decision("turn 1", decision, engine.state)

    baseline_messages = build_baseline_messages(
        [
            (
                "Analyze this input as state transition logic: 'use podman instead of docker'. "
                "First line must be ACTION:<clarify|proceed>."
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
                "First line must be ACTION:<clarify|proceed>."
            )
        ],
        premise=None,
        use_policies=[],
        prohibit_policies=[],
    )
    print_messages("reinjected-state", reinjected_messages)
    reinjected_output = complete_messages(reinjected_messages)
    print_model_output("Reinjected-state", reinjected_output)

    if decision["kind"] == DECISION_UPDATE:
        print_messages("compiler-mediated (full)", [])
        mediated_output = "[no call] authoritative state applied deterministic replacement update"
        print_model_output("Compiler-mediated (full)", mediated_output)
    else:
        print_messages("compiler-mediated (full)", [])
        mediated_output = "[no call] expected update was not produced"
        print_model_output("Compiler-mediated (full)", mediated_output)

    compacted_turns, compacted_state, compacted_prompt = compact_user_turns(user_inputs)
    if compacted_prompt is None:
        print_messages("compiler-mediated + compact", [])
        compact_output = "[no call] compaction preserved deterministic state update"
        print_model_output("Compiler-mediated + compact", compact_output)
    else:
        print_messages("compiler-mediated + compact", [])
        compact_output = "[no call] unexpected clarify was produced during compaction"
        print_model_output("Compiler-mediated + compact", compact_output)

    state_applied = not _is_initial_authoritative_state(engine.state)
    compact_state_applied = not _is_initial_authoritative_state(compacted_state)
    no_pending = not engine.has_pending_clarification()
    compact_no_pending = compacted_prompt is None

    baseline_has_authoritative_precondition = False
    reinjected_has_authoritative_precondition = False
    compiler_pass = decision["kind"] == DECISION_UPDATE and state_applied and no_pending
    compact_pass = compacted_prompt is None and compact_state_applied and compact_no_pending

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
        yes_no(decision["kind"] == DECISION_UPDATE),
        context="compiler-mediated",
    )
    print_host_check(
        "COMPILER_STATE_APPLIED",
        yes_no(state_applied),
        context="compiler-mediated",
    )

    print_spec_report(
        test_name=DEMO_NAME,
        baseline_pass=baseline_has_authoritative_precondition,
        reinjected_state_pass=reinjected_has_authoritative_precondition,
        compiler_pass=compiler_pass,
        compiler_compact_pass=compact_pass,
        expected=(
            "missing-source replacement should deterministically apply the resulting use update "
            "without pending continuation"
        ),
        actual=(
            "compiler applied deterministic replacement update; baseline and reinjected paths "
            "still lack authoritative state enforcement"
            if compiler_pass and compact_pass
            else "compiler did not consistently apply deterministic replacement behavior"
        ),
        passed=compiler_pass and compact_pass,
        result_pass="missing-source replacement applied deterministically",
        result_fail="missing-source replacement did not apply deterministically",
    )


if __name__ == "__main__":
    main()
