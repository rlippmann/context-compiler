"""Demo 9: confirmation-style followups remain ordinary no_directive."""

from collections.abc import Mapping

from context_compiler import (
    create_engine,
    is_no_directive,
    is_update,
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

DEMO_NAME = (
    "09_confirmation_no_directive_boundary — "
    "missing-source replacement does not create a confirmation state"
)
TURN_1 = "use podman instead of docker"
TURN_2 = "maybe"
TURN_3 = "yes"
INITIAL_AUTHORITATIVE_STATE = create_engine().state


def _has_podman_use(policies: Mapping[str, str]) -> bool:
    return policies.get("podman") == "use"


def _is_initial_authoritative_state(*, premise: str | None, policies: Mapping[str, str]) -> bool:
    return (
        premise == INITIAL_AUTHORITATIVE_STATE["premise"]
        and dict(policies) == INITIAL_AUTHORITATIVE_STATE["policies"]
    )


def main() -> None:
    engine = create_engine()
    user_inputs = [TURN_1, TURN_2, TURN_3]
    print_user_inputs(user_inputs)

    first = engine.step(TURN_1)
    premise, policies = observe_engine(engine)
    print_decision("turn 1", first, premise=premise, policies=policies)
    state_applied_after_first = _has_podman_use(policies)

    second = engine.step(TURN_2)
    premise, policies = observe_engine(engine)
    print_decision("turn 2", second, premise=premise, policies=policies)
    state_preserved_after_second = _has_podman_use(policies)

    third = engine.step(TURN_3)
    premise, policies = observe_engine(engine)
    print_decision("turn 3", third, premise=premise, policies=policies)

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
        compact_output = f"[no call] error required: {compacted_prompt}"
        print_model_output("Compiler-mediated + compact", compact_output)
    else:
        print_messages("compiler-mediated + compact", [])
        compact_output = (
            "[no call] compact replay kept confirmation-style followups as no_directive"
        )
        print_model_output("Compiler-mediated + compact", compact_output)

    deterministic_initial_update = is_update(first) and state_applied_after_first
    unrelated_followup_no_directive = is_no_directive(second) and state_preserved_after_second
    confirmation_token_not_consumed = is_no_directive(third)
    premise, policies = observe_engine(engine)
    deterministic_final_state = _has_podman_use(policies)
    _, compacted_policies = state_observations(compacted_state)

    baseline_has_confirmation_state_machine = False
    reinjected_has_confirmation_state_machine = False

    compiler_pass = (
        deterministic_initial_update
        and unrelated_followup_no_directive
        and confirmation_token_not_consumed
        and deterministic_final_state
    )

    compact_pass = (
        compacted_prompt is None
        and compacted_turns == [TURN_2, TURN_3]
        and _has_podman_use(compacted_policies)
    )

    print_host_check(
        "DETERMINISTIC_INITIAL_UPDATE",
        yes_no(deterministic_initial_update),
        context="compiler-mediated",
    )
    print_host_check(
        "UNRELATED_FOLLOWUP_NO_DIRECTIVE",
        yes_no(unrelated_followup_no_directive),
        context="compiler-mediated",
    )
    print_host_check(
        "CONFIRMATION_TOKEN_NOT_CONSUMED",
        yes_no(confirmation_token_not_consumed),
        context="compiler-mediated",
    )
    print_host_check(
        "FINAL_POLICY_PODMAN_PRESENT",
        yes_no(deterministic_final_state),
        context="compiler-mediated",
    )

    print_spec_report(
        test_name=DEMO_NAME,
        baseline_pass=baseline_has_confirmation_state_machine,
        reinjected_state_pass=reinjected_has_confirmation_state_machine,
        compiler_pass=compiler_pass,
        compiler_compact_pass=compact_pass,
        expected=(
            "missing-source replacement should apply without creating an engine-owned "
            "confirmation state, and later yes/no-style input should remain ordinary "
            "no_directive"
        ),
        actual=(
            "compiler applied deterministic replacement update and treated later inputs as "
            "ordinary no_directive"
            if compiler_pass and compact_pass
            else "compiler did not consistently preserve the confirmation-no_directive boundary"
        ),
        passed=compiler_pass and compact_pass,
        result_pass="missing-source replacement stayed outside engine-owned confirmation state",
        result_fail="missing-source replacement still behaved like engine-owned confirmation state",
    )


if __name__ == "__main__":
    main()
