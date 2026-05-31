"""Demo 9: pending clarification requires confirmation-only continuation."""

from context_compiler import (
    DECISION_CLARIFY,
    DECISION_UPDATE,
    POLICY_USE,
    State,
    create_engine,
    get_policy_items,
)
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

DEMO_NAME = "09_pending_clarification_continuation — confirmation-only state transition"
TURN_1 = "use podman instead of docker"
TURN_2 = "maybe"
TURN_3 = "yes"
INITIAL_AUTHORITATIVE_STATE = create_engine().state


def _has_podman_use(state: State) -> bool:
    return "podman" in get_policy_items(state, POLICY_USE)


def _is_initial_authoritative_state(state: State) -> bool:
    return state == INITIAL_AUTHORITATIVE_STATE


def main() -> None:
    engine = create_engine()
    user_inputs = [TURN_1, TURN_2, TURN_3]
    print_user_inputs(user_inputs)

    first = engine.step(TURN_1)
    print_decision("turn 1", first, engine.state)
    pending_after_first = engine.has_pending_clarification()
    state_unchanged_after_first = _is_initial_authoritative_state(engine.state)

    second = engine.step(TURN_2)
    print_decision("turn 2", second, engine.state)
    pending_after_second = engine.has_pending_clarification()
    state_unchanged_after_second = _is_initial_authoritative_state(engine.state)

    third = engine.step(TURN_3)
    print_decision("turn 3", third, engine.state)
    pending_after_third = engine.has_pending_clarification()

    baseline_messages = build_baseline_messages(
        [
            (
                "Conversation: user says 'use podman instead of docker', then 'maybe', then 'yes'. "
                "First line must be STATE_MACHINE:<deterministic|plausible>."
            )
        ],
        baseline_system_prompt="Be helpful and produce a plausible interpretation.",
    )
    print_messages("baseline", baseline_messages)
    baseline_output = complete_messages(baseline_messages)
    print_model_output("Baseline", baseline_output)

    _, reinjected_messages = build_reinjected_messages(
        [
            (
                "Conversation: user says 'use podman instead of docker', then 'maybe', then 'yes'. "
                "First line must be STATE_MACHINE:<deterministic|plausible>."
            )
        ],
        premise=None,
        use_policies=[],
        prohibit_policies=[],
    )
    print_messages("reinjected-state", reinjected_messages)
    reinjected_output = complete_messages(reinjected_messages)
    print_model_output("Reinjected-state", reinjected_output)

    print_messages("compiler-mediated (full)", [])
    mediated_output = "[no call] host-side state machine checked directly"
    print_model_output("Compiler-mediated (full)", mediated_output)

    compacted_turns, compacted_state, compacted_prompt = compact_user_turns(user_inputs)
    if compacted_prompt is not None:
        print_messages("compiler-mediated + compact", [])
        compact_output = f"[no call] clarification required: {compacted_prompt}"
        print_model_output("Compiler-mediated + compact", compact_output)
    else:
        print_messages("compiler-mediated + compact", [])
        compact_output = "[no call] compact replay resolved pending flow"
        print_model_output("Compiler-mediated + compact", compact_output)

    blocked_initial_mutation = first["kind"] == DECISION_CLARIFY and state_unchanged_after_first
    pending_preserved_on_nonconfirm = (
        second["kind"] == DECISION_CLARIFY
        and pending_after_first
        and pending_after_second
        and state_unchanged_after_first
        and state_unchanged_after_second
    )
    confirmation_only_resolution = third["kind"] == DECISION_UPDATE and not pending_after_third
    deterministic_final_state = _has_podman_use(engine.state)

    baseline_has_pending_state_machine = False
    reinjected_has_pending_state_machine = False

    compiler_pass = (
        blocked_initial_mutation
        and pending_preserved_on_nonconfirm
        and confirmation_only_resolution
        and deterministic_final_state
    )

    compact_pass = (
        compacted_prompt is not None
        and compacted_turns == [TURN_1]
        and _is_initial_authoritative_state(compacted_state)
    )

    print_host_check(
        "BLOCKED_INITIAL_MUTATION",
        yes_no(blocked_initial_mutation),
        context="compiler-mediated",
    )
    print_host_check(
        "PENDING_PRESERVED_ON_NONCONFIRM",
        yes_no(pending_preserved_on_nonconfirm),
        context="compiler-mediated",
    )
    print_host_check(
        "CONFIRMATION_ONLY_RESOLUTION",
        yes_no(confirmation_only_resolution),
        context="compiler-mediated",
    )
    print_host_check(
        "FINAL_POLICY_PODMAN_USE",
        yes_no(deterministic_final_state),
        context="compiler-mediated",
    )

    print_spec_report(
        test_name=DEMO_NAME,
        baseline_pass=baseline_has_pending_state_machine,
        reinjected_state_pass=reinjected_has_pending_state_machine,
        compiler_pass=compiler_pass,
        compiler_compact_pass=compact_pass,
        expected=(
            "replacement flow should require pending clarification, preserve pending on "
            "non-confirmation, and apply only on confirmation"
        ),
        actual=(
            "compiler enforced blocked mutation, pending continuation, and confirmation-only "
            "resolution to final podman policy"
            if compiler_pass and compact_pass
            else "compiler did not consistently enforce pending clarification continuation"
        ),
        passed=compiler_pass and compact_pass,
        result_pass="pending clarification continuation enforced deterministically",
        result_fail="pending clarification continuation not enforced deterministically",
    )


if __name__ == "__main__":
    main()
