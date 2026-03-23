import json

import pytest

from context_compiler import compile_transcript, create_engine, get_policy_items, get_premise_value
from context_compiler.engine import DecisionKind, Engine


def test_decision_kind_strenum_behavior() -> None:
    for kind in DecisionKind:
        assert kind == kind.value
        assert str(kind) == kind.value
        assert DecisionKind(kind.value) is kind


def test_initial_state_and_helpers() -> None:
    engine = create_engine()
    assert engine.state == {"premise": None, "policies": {}, "version": 2}
    assert get_premise_value(engine.state) is None
    assert get_policy_items(engine.state) == []


def test_state_getter_returns_defensive_copy() -> None:
    engine = create_engine()
    snapshot = engine.state
    snapshot["premise"] = "mutated"
    snapshot["policies"]["docker"] = "use"

    assert engine.state == {"premise": None, "policies": {}, "version": 2}


def test_export_json_returns_complete_representation_of_state() -> None:
    engine = create_engine()
    payload = engine.export_json()
    assert json.loads(payload) == {"premise": None, "policies": {}, "version": 2}


def test_export_json_is_canonical_sorted_and_compact() -> None:
    engine = create_engine()
    engine.step("use zeta")
    engine.step("use alpha")
    payload = engine.export_json()

    assert payload == '{"policies":{"alpha":"use","zeta":"use"},"premise":null,"version":2}'


def test_import_json_restores_state_exactly() -> None:
    engine = create_engine()
    expected = {
        "premise": "Use concise output",
        "policies": {"docker": "prohibit", "pytest": "use"},
        "version": 2,
    }

    engine.import_json(json.dumps(expected))

    assert engine.state == expected


def test_export_import_round_trip_preserves_state() -> None:
    source = create_engine(
        state={
            "premise": "Use concise output",
            "policies": {"docker": "prohibit", "pytest": "use"},
            "version": 2,
        }
    )

    target = create_engine()
    target.import_json(source.export_json())

    assert target.state == source.state


def test_import_json_invalid_json_and_unsupported_version_are_rejected() -> None:
    engine = create_engine()

    with pytest.raises(ValueError, match="Invalid JSON payload"):
        engine.import_json("{")

    with pytest.raises(ValueError, match="Unsupported state version"):
        engine.import_json(
            json.dumps(
                {
                    "premise": None,
                    "policies": {},
                    "version": 1,
                }
            )
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"premise": None, "version": 2},
        {"premise": [], "policies": {}, "version": 2},
        {"premise": None, "policies": [], "version": 2},
        {"premise": None, "policies": {"docker": "deny"}, "version": 2},
    ],
)
def test_import_json_rejects_structurally_invalid_payload(payload: dict[str, object]) -> None:
    engine = create_engine()
    with pytest.raises(ValueError):
        engine.import_json(json.dumps(payload))


def test_import_json_normalizes_policy_keys() -> None:
    engine = create_engine()
    engine.import_json(
        json.dumps(
            {
                "premise": None,
                "policies": {
                    " The Docker ": "prohibit",
                    "dont use": "use",
                },
                "version": 2,
            }
        )
    )

    assert engine.state == {
        "premise": None,
        "policies": {"docker": "prohibit", "don't use": "use"},
        "version": 2,
    }


def test_import_json_sanitizes_premise_value() -> None:
    engine = create_engine()
    engine.import_json(
        json.dumps(
            {
                "premise": "  Use   concise’  output  ",
                "policies": {},
                "version": 2,
            }
        )
    )

    assert engine.state["premise"] == "Use concise' output"


def test_import_json_canonicalizes_policies_by_normalized_key() -> None:
    engine = create_engine()
    engine.import_json(
        json.dumps(
            {
                "premise": None,
                "policies": {
                    "  The Docker ": "prohibit",
                    "docker": "use",
                },
                "version": 2,
            }
        )
    )

    assert engine.state["policies"] == {"docker": "use"}


def test_state_property_is_read_only() -> None:
    engine = create_engine()
    with pytest.raises(AttributeError):
        engine.state = {"premise": None, "policies": {}, "version": 2}


def test_non_matching_input_is_passthrough() -> None:
    engine = create_engine()
    before = engine.state

    for text in [
        "hello there",
        "please use docker",
        "allow docker",
        "I am using x",
        "set X",
        "no use docker",
        " don't use docker",
    ]:
        decision = engine.step(text)
        assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}

    assert engine.state == before


def test_admin_command_near_misses_are_passthrough() -> None:
    engine = create_engine()
    before = engine.state

    for text in ["clear premise ", " reset policies", "clear state\t"]:
        decision = engine.step(text)
        assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}

    assert engine.state == before


def test_clear_premise_is_idempotent_update_when_already_null() -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step("clear premise")
    assert decision == {"kind": "update", "state": before, "prompt_to_user": None}
    assert engine.state == before


def test_clear_state_is_idempotent_update_when_already_empty() -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step("clear state")
    assert decision == {"kind": "update", "state": before, "prompt_to_user": None}
    assert engine.state == before


def test_set_premise_lifecycle_rules() -> None:
    engine = create_engine()

    d1 = engine.step("set premise   concise   replies")
    assert d1["kind"] == "update"
    assert engine.state["premise"] == "concise replies"

    before = engine.state
    d2 = engine.step("set premise new")
    assert d2["kind"] == "clarify"
    assert engine.state == before


def test_set_premise_empty_payload_clarifies_without_mutation() -> None:
    engine = create_engine()
    before = engine.state
    d1 = engine.step("set premise")
    assert d1["kind"] == "clarify"
    assert engine.state == before


def test_set_premise_whitespace_payload_clarifies_without_mutation() -> None:
    engine = create_engine()
    before = engine.state
    d1 = engine.step("set premise    ")
    assert d1["kind"] == "clarify"
    assert engine.state == before


def test_change_premise_requires_existing_premise() -> None:
    engine = create_engine()

    d1 = engine.step("change premise to concise")
    assert d1["kind"] == "clarify"
    assert engine.state == {"premise": None, "policies": {}, "version": 2}

    engine.step("set premise first")
    d2 = engine.step("change premise to second")
    assert d2["kind"] == "update"
    assert engine.state["premise"] == "second"


def test_change_premise_to_empty_payload_clarifies_without_mutation() -> None:
    engine = create_engine()
    engine.step("set premise baseline")
    before = engine.state

    d1 = engine.step("change premise to")
    assert d1["kind"] == "clarify"
    assert engine.state == before


def test_change_premise_to_whitespace_payload_clarifies_without_mutation() -> None:
    engine = create_engine()
    engine.step("set premise baseline")
    before = engine.state

    d1 = engine.step("change premise to    ")
    assert d1["kind"] == "clarify"
    assert engine.state == before


def test_clear_premise_and_clear_state() -> None:
    engine = create_engine()
    engine.step("set premise use bullets")
    engine.step("use docker")

    d1 = engine.step("clear premise")
    assert d1["kind"] == "update"
    assert engine.state == {"premise": None, "policies": {"docker": "use"}, "version": 2}

    d2 = engine.step("clear state")
    assert d2["kind"] == "update"
    assert engine.state == {"premise": None, "policies": {}, "version": 2}


def test_policy_directives_and_idempotent_update() -> None:
    engine = create_engine()

    d1 = engine.step("use   The Docker")
    assert d1["kind"] == "update"
    assert engine.state["policies"] == {"docker": "use"}

    d2 = engine.step("use docker")
    assert d2["kind"] == "update"
    assert engine.state["policies"] == {"docker": "use"}

    d3 = engine.step("don't use docker")
    assert d3["kind"] == "clarify"
    assert engine.state["policies"] == {"docker": "use"}

    engine2 = create_engine()
    engine2.step("don't use docker")
    d4 = engine2.step("don't use docker")
    assert d4["kind"] == "update"
    assert engine2.state["policies"] == {"docker": "prohibit"}

    d5 = engine2.step("use docker")
    assert d5["kind"] == "clarify"
    assert engine2.state["policies"] == {"docker": "prohibit"}


def test_reset_policies_is_update_even_when_already_empty() -> None:
    engine = create_engine()
    d1 = engine.step("reset policies")
    assert d1["kind"] == "update"
    assert engine.state == {"premise": None, "policies": {}, "version": 2}

    engine.step("use docker")
    d2 = engine.step("reset policies")
    assert d2["kind"] == "update"
    assert engine.state == {"premise": None, "policies": {}, "version": 2}


def test_replace_use_success() -> None:
    engine = create_engine()
    engine.step("use docker")

    decision = engine.step("use kubectl instead of docker")

    assert decision["kind"] == "update"
    assert engine.state["policies"] == {"kubectl": "use"}


def test_replace_use_identity_is_noop_update() -> None:
    engine = create_engine()
    engine.step("use docker")
    before = engine.state

    decision = engine.step("use the docker instead of docker")

    assert decision["kind"] == "update"
    assert engine.state == before


def test_replace_use_missing_source_state_enters_replacement_intent_clarify() -> None:
    engine = create_engine()

    d1 = engine.step("use kubectl instead of docker")
    assert d1 == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": 'Did you mean to use "kubectl" instead?',
    }
    assert engine.state == {"premise": None, "policies": {}, "version": 2}


def test_replace_use_missing_source_yes_confirmation_applies_use_only() -> None:
    engine = create_engine()

    first = engine.step("use kubectl instead of docker")
    assert first == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": 'Did you mean to use "kubectl" instead?',
    }
    assert engine.state == {"premise": None, "policies": {}, "version": 2}

    second = engine.step("yes")
    assert second["kind"] == "update"
    assert engine.state == {
        "premise": None,
        "policies": {"kubectl": "use"},
        "version": 2,
    }


def test_replace_use_missing_source_no_confirmation_has_no_mutation() -> None:
    engine = create_engine()
    engine.step("use kubectl instead of docker")
    before = engine.state

    decision = engine.step("no")
    assert decision == {"kind": "update", "state": before, "prompt_to_user": None}
    assert engine.state == before


def test_replace_use_missing_source_takes_priority_over_target_prohibit_prompt() -> None:
    engine = create_engine()
    engine.step("don't use kubectl")

    decision = engine.step("use kubectl instead of docker")
    assert decision == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": 'Did you mean to use "kubectl" instead?',
    }


def test_replace_use_ky_prohibit_enters_replacement_intent_clarify() -> None:
    engine = create_engine()
    engine.step("don't use docker")
    engine.step("use pytest")

    first = engine.step("use kubectl instead of docker")
    expected = (
        '"docker" is currently prohibited. Did you mean to remove it and use "kubectl" instead?'
    )
    assert first == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": expected,
    }
    assert engine.state["policies"] == {"docker": "prohibit", "pytest": "use"}

    second = engine.step("yes")
    assert second["kind"] == "update"
    assert engine.state["policies"] == {"kubectl": "use", "pytest": "use"}


def test_replace_use_ky_prohibit_no_confirmation_has_no_mutation() -> None:
    engine = create_engine()
    engine.step("don't use docker")
    engine.step("use pytest")
    engine.step("use kubectl instead of docker")
    before = engine.state

    decision = engine.step("no")
    assert decision == {"kind": "update", "state": before, "prompt_to_user": None}
    assert engine.state == before


def test_replace_use_kx_prohibit_enters_replacement_intent_clarify() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("don't use kubectl")

    first = engine.step("use kubectl instead of docker")
    expected = (
        '"kubectl" is currently prohibited. Did you mean to remove "docker" '
        'and use "kubectl" instead?'
    )
    assert first == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": expected,
    }
    assert engine.state["policies"] == {"docker": "use", "kubectl": "prohibit"}

    second = engine.step("yes")
    assert second["kind"] == "update"
    assert engine.state["policies"] == {"kubectl": "use"}


def test_replace_use_priority_prefers_source_prohibit_prompt_when_both_prohibit() -> None:
    engine = create_engine()
    engine.step("don't use docker")
    engine.step("don't use kubectl")

    first = engine.step("use kubectl instead of docker")
    expected = (
        '"docker" is currently prohibited. Did you mean to remove it and use "kubectl" instead?'
    )
    assert first == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": expected,
    }
    assert engine.state["policies"] == {"docker": "prohibit", "kubectl": "prohibit"}


def test_replace_use_kx_prohibit_no_confirmation_has_no_mutation() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("don't use kubectl")
    engine.step("use kubectl instead of docker")
    before = engine.state

    decision = engine.step("no")
    assert decision == {"kind": "update", "state": before, "prompt_to_user": None}
    assert engine.state == before


def test_pending_confirmation_precedence_and_resolution() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("don't use kubectl")
    first = engine.step("use kubectl instead of docker")

    # While pending, directive parsing is suspended.
    second = engine.step("use docker")
    assert second == first
    assert engine.state["policies"] == {"docker": "use", "kubectl": "prohibit"}

    third = engine.step("yes")
    assert third["kind"] == "update"
    assert engine.state["policies"] == {"kubectl": "use"}


def test_pending_negative_discards_proposed_event() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("don't use kubectl")
    engine.step("use kubectl instead of docker")
    before = engine.state

    decision = engine.step("no")

    assert decision == {"kind": "update", "state": before, "prompt_to_user": None}
    assert engine.state["policies"] == {"docker": "use", "kubectl": "prohibit"}


def test_pending_confirmation_token_normalization() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("don't use kubectl")
    engine.step("use kubectl instead of docker")

    decision = engine.step("  YES!!!  ")
    assert decision["kind"] == "update"
    assert engine.state["policies"] == {"kubectl": "use"}


def test_pending_affirmative_confirmation_token_variants_are_accepted() -> None:
    for token in ["yes please", "Yep", "yeah", "ok", "  OKAY...  ", "sure!"]:
        engine = create_engine()
        engine.step("use docker")
        engine.step("don't use kubectl")
        engine.step("use kubectl instead of docker")
        decision = engine.step(token)
        assert decision["kind"] == "update"
        assert engine.state["policies"] == {"kubectl": "use"}


def test_pending_negative_confirmation_token_normalization_no_punctuation() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("don't use kubectl")
    engine.step("use kubectl instead of docker")
    before = engine.state

    decision = engine.step("  NO!!!  ")
    assert decision == {"kind": "update", "state": before, "prompt_to_user": None}
    assert engine.state == before


def test_pending_negative_confirmation_token_normalization_no_thanks() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("don't use kubectl")
    engine.step("use kubectl instead of docker")
    before = engine.state

    decision = engine.step("no thanks.")
    assert decision == {"kind": "update", "state": before, "prompt_to_user": None}
    assert engine.state == before


def test_pending_negative_confirmation_token_variants_are_accepted() -> None:
    for token in ["nope", "Nope??", " no ", "NO THANKS!"]:
        engine = create_engine()
        engine.step("use docker")
        engine.step("don't use kubectl")
        engine.step("use kubectl instead of docker")
        before = engine.state
        decision = engine.step(token)
        assert decision == {"kind": "update", "state": before, "prompt_to_user": None}
        assert engine.state == before


def test_pending_unmatched_input_remains_clarify_without_mutation() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("don't use kubectl")
    first = engine.step("use kubectl instead of docker")
    before = engine.state

    second = engine.step("maybe")
    assert second == first
    assert engine.state == before


def test_pending_unmatched_input_can_repeat_without_mutation() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("don't use kubectl")
    first = engine.step("use kubectl instead of docker")
    before = engine.state

    assert engine.step("later") == first
    assert engine.step("still later") == first
    assert engine.state == before


def test_replacement_pending_yes_can_override_conflicting_target_polarity() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("don't use kubectl")

    first = engine.step("use kubectl instead of docker")
    assert first["kind"] == "clarify"
    assert engine.state["policies"] == {"docker": "use", "kubectl": "prohibit"}

    second = engine.step("yes")
    assert second["kind"] == "update"
    assert engine.state["policies"] == {"kubectl": "use"}


def test_import_json_clears_pending_clarification_yes_no_not_confirmation() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("don't use kubectl")
    first = engine.step("use kubectl instead of docker")
    assert first["kind"] == "clarify"

    imported = {"premise": "baseline", "policies": {"pytest": "use"}, "version": 2}
    engine.import_json(json.dumps(imported))

    yes_decision = engine.step("yes")
    assert yes_decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == imported

    no_decision = engine.step("no")
    assert no_decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == imported


def test_compile_transcript_ignores_non_user_messages() -> None:
    result = compile_transcript(
        [
            {"role": "system", "content": "set premise concise"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "set premise concise"},
        ]
    )

    assert result == {
        "kind": "state",
        "state": {"premise": "concise", "policies": {}, "version": 2},
    }


def test_apply_transcript_matches_manual_step_replay() -> None:
    messages: list[dict[str, object]] = [
        {"role": "assistant", "content": "ignore me"},
        {"role": "user", "content": "set premise concise"},
        {"role": "user", "content": "use docker"},
    ]

    replay_engine = create_engine()
    replay_result = replay_engine.apply_transcript(messages)

    manual_engine = create_engine()
    manual_result: dict[str, object] = {"kind": "state", "state": manual_engine.state}
    for message in messages:
        if message.get("role") != "user" or not isinstance(message.get("content"), str):
            continue
        manual_engine.step(message["content"])
        manual_result = {"kind": "state", "state": manual_engine.state}

    assert replay_result == manual_result
    assert replay_engine.state == manual_engine.state


def test_constructor_with_state_initializes_from_valid_state() -> None:
    state = {"premise": "Prefer bullets", "policies": {"pytest": "use"}, "version": 2}
    engine = Engine(state=state)
    assert engine.state == state
