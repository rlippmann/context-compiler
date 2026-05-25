"""Demo 8: replacement precondition is enforced by authoritative state."""

from context_compiler import DECISION_CLARIFY, State, create_engine
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

DEMO_NAME = "08_replacement_precondition — invalid replacement blocked"
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

    if decision["kind"] == DECISION_CLARIFY:
        print_messages("compiler-mediated (full)", [])
        mediated_output = f"[no call] clarification required: {decision['prompt_to_user']}"
        print_model_output("Compiler-mediated (full)", mediated_output)
    else:
        print_messages("compiler-mediated (full)", [])
        mediated_output = "[no call] expected clarify was not produced"
        print_model_output("Compiler-mediated (full)", mediated_output)

    compacted_turns, compacted_state, compacted_prompt = compact_user_turns(user_inputs)
    if compacted_prompt is not None:
        print_messages("compiler-mediated + compact", [])
        compact_output = f"[no call] clarification required: {compacted_prompt}"
        print_model_output("Compiler-mediated + compact", compact_output)
    else:
        print_messages("compiler-mediated + compact", [])
        compact_output = "[no call] expected clarify was not produced"
        print_model_output("Compiler-mediated + compact", compact_output)

    state_unchanged = _is_initial_authoritative_state(engine.state)
    compact_state_unchanged = _is_initial_authoritative_state(compacted_state)
    no_pending = engine.has_pending_clarification()
    compact_pending = compacted_prompt is not None

    baseline_has_authoritative_precondition = False
    reinjected_has_authoritative_precondition = False
    compiler_pass = decision["kind"] == DECISION_CLARIFY and state_unchanged and no_pending
    compact_pass = compacted_prompt is not None and compact_state_unchanged and compact_pending

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
        yes_no(decision["kind"] == DECISION_CLARIFY),
        context="compiler-mediated",
    )
    print_host_check(
        "COMPILER_STATE_UNCHANGED",
        yes_no(state_unchanged),
        context="compiler-mediated",
    )

    print_spec_report(
        test_name=DEMO_NAME,
        baseline_pass=baseline_has_authoritative_precondition,
        reinjected_state_pass=reinjected_has_authoritative_precondition,
        compiler_pass=compiler_pass,
        compiler_compact_pass=compact_pass,
        expected=(
            "invalid replacement should be blocked with clarification and no authoritative state "
            "mutation"
        ),
        actual=(
            "compiler blocked invalid replacement and preserved state; baseline and reinjected "
            "paths have no authoritative replacement precondition"
            if compiler_pass and compact_pass
            else "compiler did not consistently enforce replacement precondition behavior"
        ),
        passed=compiler_pass and compact_pass,
        result_pass="invalid replacement precondition enforced deterministically",
        result_fail="invalid replacement precondition not enforced deterministically",
    )


if __name__ == "__main__":
    main()
