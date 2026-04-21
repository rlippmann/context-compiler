import json

import pytest

from context_compiler import compile_transcript, create_engine, get_policy_items, get_premise_value
from context_compiler.engine import DecisionKind, Engine

pytestmark = pytest.mark.contract


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


def test_get_policy_items_filters_by_policy_value_sorted() -> None:
    engine = create_engine()
    engine.step("use zeta")
    engine.step("prohibit docker")
    engine.step("use alpha")

    assert get_policy_items(engine.state, "use") == ["alpha", "zeta"]
    assert get_policy_items(engine.state, "prohibit") == ["docker"]


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


def test_import_json_rejects_non_object_payload() -> None:
    engine = create_engine()
    with pytest.raises(ValueError, match="Invalid state payload"):
        engine.import_json('["not", "an", "object"]')


def test_import_json_rejects_non_string_policy_keys() -> None:
    payload = {
        "premise": None,
        "policies": {1: "use"},
        "version": 2,
    }
    with pytest.raises(ValueError, match="Invalid state payload"):
        create_engine(state=payload)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "policies",
    [
        {"A": "use", "a": "use"},
        {"a": "use"},
        {"the": "use"},
    ],
)
def test_import_json_rejects_policy_keys_that_normalize_to_empty(
    policies: dict[str, str],
) -> None:
    engine = create_engine()
    with pytest.raises(ValueError, match="Invalid state payload"):
        engine.import_json(
            json.dumps(
                {
                    "premise": None,
                    "policies": policies,
                    "version": 2,
                }
            )
        )


@pytest.mark.contract
def test_export_checkpoint_contains_version_authoritative_state_and_pending_none() -> None:
    engine = create_engine()
    engine.step("set premise concise")
    engine.step("use docker")

    checkpoint = engine.export_checkpoint()

    assert checkpoint == {
        "checkpoint_version": 1,
        "authoritative_state": {
            "premise": "concise",
            "policies": {"docker": "use"},
            "version": 2,
        },
        "pending": None,
    }


@pytest.mark.contract
def test_export_checkpoint_json_round_trip_preserves_authoritative_and_pending_state() -> None:
    source = create_engine()
    source.step("use kubectl instead of docker")

    payload = source.export_checkpoint_json()
    target = create_engine()
    target.import_checkpoint_json(payload)

    assert target.export_checkpoint() == source.export_checkpoint()


@pytest.mark.contract
def test_export_checkpoint_json_is_canonical_sorted_and_compact() -> None:
    engine = create_engine()
    engine.step("set premise concise")
    engine.step("use zeta")
    engine.step("use alpha")

    payload = engine.export_checkpoint_json()

    assert payload == (
        '{"authoritative_state":{"policies":{"alpha":"use","zeta":"use"},'
        '"premise":"concise","version":2},"checkpoint_version":1,"pending":null}'
    )


@pytest.mark.contract
def test_export_checkpoint_serializes_pending_replacement_state_for_exact_resume() -> None:
    engine = create_engine()
    clarify = engine.step("use kubectl instead of docker")
    assert clarify["kind"] == "clarify"

    checkpoint = engine.export_checkpoint()
    assert checkpoint["pending"] == {
        "kind": "replacement",
        "replacement": {
            "kind": "use_only",
            "new_item": "kubectl",
            "old_item": None,
        },
        "prompt_to_user": (
            'No exact policy found for "docker".\n'
            "Replacement requires an exact policy match.\n"
            'Confirm to use "kubectl" and keep existing policies?'
        ),
    }


@pytest.mark.contract
def test_export_checkpoint_serializes_replace_use_pending_and_round_trips() -> None:
    source = create_engine()
    source.step("use docker")
    source.step("prohibit kubectl")
    clarify = source.step("use kubectl instead of docker")
    assert clarify["kind"] == "clarify"

    checkpoint = source.export_checkpoint()
    assert checkpoint["pending"] == {
        "kind": "replacement",
        "replacement": {
            "kind": "replace_use",
            "new_item": "kubectl",
            "old_item": "docker",
        },
        "prompt_to_user": (
            '"kubectl" is currently prohibited. Did you mean to remove "docker" '
            'and use "kubectl" instead?'
        ),
    }

    yes_target = create_engine()
    yes_target.import_checkpoint(checkpoint)
    yes_decision = yes_target.step("yes")
    assert yes_decision["kind"] == "update"
    assert yes_target.state == {"premise": None, "policies": {"kubectl": "use"}, "version": 2}

    no_target = create_engine()
    no_target.import_checkpoint(checkpoint)
    before_no = no_target.state
    no_decision = no_target.step("no")
    assert no_decision == {"kind": "update", "state": before_no, "prompt_to_user": None}
    assert no_target.state == {
        "premise": None,
        "policies": {"docker": "use", "kubectl": "prohibit"},
        "version": 2,
    }


@pytest.mark.contract
def test_import_checkpoint_restores_pending_clarification_and_unmatched_input_reuses_prompt() -> (
    None
):
    source = create_engine()
    first = source.step("use kubectl instead of docker")
    assert first["kind"] == "clarify"
    checkpoint = source.export_checkpoint()

    target = create_engine()
    target.import_checkpoint(checkpoint)
    before = target.state
    second = target.step("maybe")

    assert second == first
    assert target.state == before


@pytest.mark.contract
def test_export_checkpoint_json_object_and_restore_paths_are_behaviorally_equivalent() -> None:
    source = create_engine()
    source.step("use kubectl instead of docker")

    checkpoint_obj = source.export_checkpoint()
    checkpoint_json = source.export_checkpoint_json()
    assert json.loads(checkpoint_json) == checkpoint_obj

    via_obj = create_engine()
    via_obj.import_checkpoint(checkpoint_obj)

    via_json = create_engine()
    via_json.import_checkpoint_json(checkpoint_json)

    assert via_obj.step("yes") == via_json.step("yes")
    assert via_obj.state == via_json.state


@pytest.mark.contract
def test_import_checkpoint_restores_pending_clarification_and_resolves_yes() -> None:
    source = create_engine()
    source.step("use kubectl instead of docker")
    checkpoint = source.export_checkpoint()

    target = create_engine()
    target.import_checkpoint(checkpoint)
    decision = target.step("yes")

    assert decision["kind"] == "update"
    assert target.state == {"premise": None, "policies": {"kubectl": "use"}, "version": 2}


def test_import_checkpoint_invalid_json_and_invalid_object_payload_are_rejected() -> None:
    engine = create_engine()

    with pytest.raises(ValueError, match="Invalid JSON payload"):
        engine.import_checkpoint_json("{")

    with pytest.raises(ValueError, match="Invalid checkpoint payload"):
        engine.import_checkpoint(  # type: ignore[arg-type]
            {
                "checkpoint_version": 1,
                "authoritative_state": {"premise": None, "policies": {}, "version": 2},
            }
        )


def test_import_checkpoint_rejects_authoritative_state_with_empty_normalized_policy_key() -> None:
    engine = create_engine()
    with pytest.raises(ValueError, match="Invalid state payload"):
        engine.import_checkpoint(  # type: ignore[arg-type]
            {
                "checkpoint_version": 1,
                "authoritative_state": {
                    "premise": None,
                    "policies": {"a": "use"},
                    "version": 2,
                },
                "pending": None,
            }
        )


def test_import_checkpoint_json_rejects_authoritative_state_with_empty_normalized_policy_key() -> (
    None
):
    engine = create_engine()
    with pytest.raises(ValueError, match="Invalid state payload"):
        engine.import_checkpoint_json(
            json.dumps(
                {
                    "checkpoint_version": 1,
                    "authoritative_state": {
                        "premise": None,
                        "policies": {"a": "use"},
                        "version": 2,
                    },
                    "pending": None,
                }
            )
        )


def test_import_checkpoint_rejects_non_object_payload() -> None:
    engine = create_engine()
    with pytest.raises(ValueError, match="Invalid checkpoint payload"):
        engine.import_checkpoint([])  # type: ignore[arg-type]


def test_import_checkpoint_rejects_unsupported_checkpoint_version() -> None:
    engine = create_engine()
    with pytest.raises(ValueError, match="Unsupported checkpoint version"):
        engine.import_checkpoint(  # type: ignore[arg-type]
            {
                "checkpoint_version": 2,
                "authoritative_state": {"premise": None, "policies": {}, "version": 2},
                "pending": None,
            }
        )


def test_import_checkpoint_json_rejects_unsupported_checkpoint_version() -> None:
    engine = create_engine()
    with pytest.raises(ValueError, match="Unsupported checkpoint version"):
        engine.import_checkpoint_json(
            json.dumps(
                {
                    "checkpoint_version": 2,
                    "authoritative_state": {"premise": None, "policies": {}, "version": 2},
                    "pending": None,
                }
            )
        )


@pytest.mark.parametrize(
    "pending",
    [
        "bad",
        {"kind": "replacement"},
        {
            "kind": "wrong",
            "replacement": {"kind": "use_only", "new_item": "x", "old_item": None},
            "prompt_to_user": "p",
        },
        {
            "kind": "replacement",
            "replacement": {"kind": "use_only", "new_item": "x", "old_item": None},
            "prompt_to_user": 1,
        },
    ],
)
def test_import_checkpoint_rejects_invalid_pending_payload_shapes(pending: object) -> None:
    engine = create_engine()
    with pytest.raises(ValueError, match="Invalid checkpoint payload"):
        engine.import_checkpoint(  # type: ignore[arg-type]
            {
                "checkpoint_version": 1,
                "authoritative_state": {"premise": None, "policies": {}, "version": 2},
                "pending": pending,
            }
        )


@pytest.mark.parametrize(
    "replacement",
    [
        "bad",
        {"kind": "use_only", "new_item": "x"},
        {"kind": "other", "new_item": "x", "old_item": None},
        {"kind": "use_only", "new_item": 1, "old_item": None},
        {"kind": "use_only", "new_item": "x", "old_item": "y"},
        {"kind": "replace_use", "new_item": "x", "old_item": None},
    ],
)
def test_import_checkpoint_rejects_invalid_pending_replacement_payload_shapes(
    replacement: object,
) -> None:
    engine = create_engine()
    with pytest.raises(ValueError, match="Invalid checkpoint payload"):
        engine.import_checkpoint(  # type: ignore[arg-type]
            {
                "checkpoint_version": 1,
                "authoritative_state": {"premise": None, "policies": {}, "version": 2},
                "pending": {
                    "kind": "replacement",
                    "replacement": replacement,
                    "prompt_to_user": "confirm?",
                },
            }
        )


def test_import_checkpoint_is_all_or_nothing_when_pending_is_invalid() -> None:
    engine = create_engine()
    engine.step("set premise baseline")
    before = engine.state

    with pytest.raises(ValueError, match="Invalid checkpoint payload"):
        engine.import_checkpoint(  # type: ignore[arg-type]
            {
                "checkpoint_version": 1,
                "authoritative_state": {
                    "premise": "new premise",
                    "policies": {"pytest": "use"},
                    "version": 2,
                },
                "pending": {
                    "kind": "replacement",
                    "replacement": {
                        "kind": "use_only",
                        "new_item": "kubectl",
                        "old_item": "docker",
                    },
                    "prompt_to_user": "confirm?",
                },
            }
        )

    assert engine.state == before


def test_import_checkpoint_is_all_or_nothing_when_authoritative_state_is_invalid() -> None:
    engine = create_engine()
    first = engine.step("use kubectl instead of docker")
    assert first["kind"] == "clarify"
    before = engine.state

    with pytest.raises(ValueError, match="Invalid state payload"):
        engine.import_checkpoint(  # type: ignore[arg-type]
            {
                "checkpoint_version": 1,
                "authoritative_state": {
                    "premise": None,
                    "policies": [],
                    "version": 2,
                },
                "pending": None,
            }
        )

    second = engine.step("maybe")
    assert second == first
    assert engine.state == before


def test_replace_use_clarifies_when_old_policy_is_not_use_in_invalid_internal_state() -> None:
    engine = create_engine()
    # Defensive-path coverage for impossible external state values.
    engine._state["policies"]["docker"] = "invalid"  # type: ignore[assignment]

    decision = engine.step("use kubectl instead of docker")

    assert decision == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": (
            "'docker' is not a use policy.\n"
            "Replacement requires an existing use policy.\n"
            "Use 'reset policies' to change it."
        ),
    }


@pytest.mark.contract
def test_import_checkpoint_with_pending_none_clears_existing_pending() -> None:
    engine = create_engine()
    engine.step("use kubectl instead of docker")

    engine.import_checkpoint(
        {
            "checkpoint_version": 1,
            "authoritative_state": {
                "premise": "baseline",
                "policies": {"pytest": "use"},
                "version": 2,
            },
            "pending": None,
        }
    )

    yes_decision = engine.step("yes")
    assert yes_decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == {"premise": "baseline", "policies": {"pytest": "use"}, "version": 2}


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
        "don't use docker",
        " prohibit docker",
    ]:
        decision = engine.step(text)
        assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}

    assert engine.state == before


def test_admin_command_near_misses_are_passthrough() -> None:
    engine = create_engine()
    before = engine.state

    for text in ["clear premise ", " reset policies", "clear state\t", " remove policy docker"]:
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


def test_set_premise_to_variant_clarifies_with_canonical_suggestion_without_mutation() -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step("set premise to concise replies")
    assert decision == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": "Did you mean 'set premise concise replies'?",
    }
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


def test_change_premise_to_without_space_payload_clarifies_after_near_miss() -> None:
    engine = create_engine()
    engine.step("set premise baseline")
    before = engine.state

    # Near-miss should not create pending; canonical empty form still clarifies.
    near_miss = engine.step("change premise baseline")
    assert near_miss == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": "Did you mean 'change premise to baseline'?",
    }

    decision = engine.step("change premise to")
    assert decision == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": (
            "Premise value cannot be empty.\nUse 'change premise to ...' with a non-empty value."
        ),
    }
    assert engine.state == before


def test_change_premise_to_whitespace_payload_clarifies_without_mutation() -> None:
    engine = create_engine()
    engine.step("set premise baseline")
    before = engine.state

    d1 = engine.step("change premise to    ")
    assert d1["kind"] == "clarify"
    assert engine.state == before


def test_change_premise_missing_to_variant_clarifies_without_mutation() -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step("change premise concise replies")
    assert decision == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": "Did you mean 'change premise to concise replies'?",
    }
    assert engine.state == before


def test_canonical_premise_forms_still_update_normally() -> None:
    engine = create_engine()

    first = engine.step("set premise concise replies")
    second = engine.step("change premise to concise bullet points")

    assert first["kind"] == "update"
    assert second["kind"] == "update"
    assert engine.state["premise"] == "concise bullet points"


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

    d3 = engine.step("prohibit docker")
    assert d3["kind"] == "clarify"
    assert d3["prompt_to_user"] == (
        "'docker' is already in use.\n"
        "Only one policy per item is allowed.\n"
        "Use 'reset policies' to change it."
    )
    assert engine.state["policies"] == {"docker": "use"}

    engine2 = create_engine()
    engine2.step("prohibit docker")
    d4 = engine2.step("prohibit docker")
    assert d4["kind"] == "update"
    assert engine2.state["policies"] == {"docker": "prohibit"}

    d5 = engine2.step("use docker")
    assert d5["kind"] == "clarify"
    assert d5["prompt_to_user"] == (
        "'docker' is already prohibited.\n"
        "Only one policy per item is allowed.\n"
        "Use 'reset policies' to change it."
    )
    assert engine2.state["policies"] == {"docker": "prohibit"}


def test_use_empty_payload_clarifies_without_mutation() -> None:
    engine = create_engine()
    before = engine.state
    expected = "Policy item cannot be empty.\nUse 'use <item>' with a non-empty value."

    for text in ["use", "use ", "use    "]:
        decision = engine.step(text)
        assert decision == {
            "kind": "clarify",
            "state": None,
            "prompt_to_user": expected,
        }
        assert engine.state == before


def test_prohibit_empty_payload_clarifies_without_mutation() -> None:
    engine = create_engine()
    before = engine.state
    expected = "Policy item cannot be empty.\nUse 'prohibit <item>' with a non-empty value."

    for text in ["prohibit", "prohibit ", "prohibit    "]:
        decision = engine.step(text)
        assert decision == {
            "kind": "clarify",
            "state": None,
            "prompt_to_user": expected,
        }
        assert engine.state == before


def test_replace_use_incomplete_payload_clarifies_without_mutation() -> None:
    engine = create_engine()
    before = engine.state
    expected = (
        "Replacement requires both new and old items.\n"
        "Use 'use <new item> instead of <old item>' with non-empty values."
    )

    for text in [
        "use x instead of",
        "use x instead of ",
        "use  instead of y",
        "use   instead of y",
        "use instead of y",
    ]:
        decision = engine.step(text)
        assert decision == {
            "kind": "clarify",
            "state": None,
            "prompt_to_user": expected,
        }
        assert engine.state == before


def test_reset_policies_is_update_even_when_already_empty() -> None:
    engine = create_engine()
    d1 = engine.step("reset policies")
    assert d1["kind"] == "update"
    assert engine.state == {"premise": None, "policies": {}, "version": 2}

    engine.step("use docker")
    d2 = engine.step("reset policies")
    assert d2["kind"] == "update"
    assert engine.state == {"premise": None, "policies": {}, "version": 2}


def test_remove_policy_removes_existing_use_policy() -> None:
    engine = create_engine()
    engine.step("use docker")

    decision = engine.step("remove policy docker")

    assert decision["kind"] == "update"
    assert engine.state == {"premise": None, "policies": {}, "version": 2}


def test_remove_policy_removes_existing_prohibit_policy() -> None:
    engine = create_engine()
    engine.step("prohibit docker")

    decision = engine.step("remove policy docker")

    assert decision["kind"] == "update"
    assert engine.state == {"premise": None, "policies": {}, "version": 2}


def test_remove_policy_missing_item_is_idempotent_update() -> None:
    engine = create_engine()
    engine.step("use docker")
    before = engine.state

    decision = engine.step("remove policy podman")

    assert decision == {"kind": "update", "state": before, "prompt_to_user": None}
    assert engine.state == before


def test_remove_policy_empty_payload_clarifies_without_mutation() -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step("remove policy")

    assert decision == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": (
            "Policy item cannot be empty.\nUse 'remove policy <item>' with a non-empty value."
        ),
    }
    assert engine.state == before


def test_remove_policy_whitespace_payload_clarifies_without_mutation() -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step("remove policy    ")

    assert decision == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": (
            "Policy item cannot be empty.\nUse 'remove policy <item>' with a non-empty value."
        ),
    }
    assert engine.state == before


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
    expected_prompt = (
        'No exact policy found for "docker".\n'
        "Replacement requires an exact policy match.\n"
        'Confirm to use "kubectl" and keep existing policies?'
    )

    d1 = engine.step("use kubectl instead of docker")
    assert d1 == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": expected_prompt,
    }
    assert engine.state == {"premise": None, "policies": {}, "version": 2}


def test_replace_use_missing_source_yes_confirmation_applies_use_only() -> None:
    engine = create_engine()
    expected_prompt = (
        'No exact policy found for "docker".\n'
        "Replacement requires an exact policy match.\n"
        'Confirm to use "kubectl" and keep existing policies?'
    )

    first = engine.step("use kubectl instead of docker")
    assert first == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": expected_prompt,
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
    engine.step("prohibit kubectl")
    expected_prompt = (
        'No exact policy found for "docker".\n'
        "Replacement requires an exact policy match.\n"
        'Confirm to use "kubectl" and keep existing policies?'
    )

    decision = engine.step("use kubectl instead of docker")
    assert decision == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": expected_prompt,
    }


def test_replace_use_missing_source_prompt_includes_contains_diagnostic_hints() -> None:
    engine = create_engine()
    engine.step("use python and docker")

    decision = engine.step("use kubectl instead of python")
    assert decision["kind"] == "clarify"
    prompt = decision["prompt_to_user"] or ""
    assert 'No exact policy found for "python".' in prompt
    assert "Replacement requires an exact policy match." in prompt
    assert 'Existing policies containing that text: "python and docker".' in prompt
    assert prompt.endswith('Confirm to use "kubectl" and keep "python and docker"?')


def test_replace_use_missing_source_prompt_lists_multiple_diagnostic_hints_sorted() -> None:
    engine = create_engine()
    engine.step("use python and docker")
    engine.step("prohibit python tooling")

    decision = engine.step("use kubectl instead of python")
    assert decision["kind"] == "clarify"
    prompt = decision["prompt_to_user"] or ""
    assert 'No exact policy found for "python".' in prompt
    assert "Replacement requires an exact policy match." in prompt
    assert (
        'Existing policies containing that text: "python and docker", "python tooling".' in prompt
    )
    assert prompt.endswith(
        'Confirm to use "kubectl" and keep "python and docker", "python tooling"?'
    )


def test_replace_use_missing_source_with_empty_normalized_probe_omits_diagnostic_hints() -> None:
    engine = create_engine()
    engine.step("use python and docker")
    before = engine.state

    decision = engine.step("use kubectl instead of the")
    assert decision["kind"] == "clarify"
    prompt = decision["prompt_to_user"] or ""
    assert 'No exact policy found for "the".' in prompt
    assert "Replacement requires an exact policy match." in prompt
    assert "Existing policies containing that text:" not in prompt
    assert engine.state == before


def test_replace_use_ky_prohibit_enters_replacement_intent_clarify() -> None:
    engine = create_engine()
    engine.step("prohibit docker")
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
    engine.step("prohibit docker")
    engine.step("use pytest")
    engine.step("use kubectl instead of docker")
    before = engine.state

    decision = engine.step("no")
    assert decision == {"kind": "update", "state": before, "prompt_to_user": None}
    assert engine.state == before


def test_replace_use_kx_prohibit_enters_replacement_intent_clarify() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")

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
    engine.step("prohibit docker")
    engine.step("prohibit kubectl")

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


def test_replace_use_invalid_source_state_prohibit_clarifies_without_mutation() -> None:
    engine = create_engine()
    engine.step("prohibit docker")
    engine.step("use pytest")
    before = engine.state

    decision = engine.step("use kubectl instead of docker")
    assert decision == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": (
            '"docker" is currently prohibited. Did you mean to remove it and use "kubectl" instead?'
        ),
    }
    assert engine.state == before


def test_replace_use_kx_prohibit_no_confirmation_has_no_mutation() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")
    engine.step("use kubectl instead of docker")
    before = engine.state

    decision = engine.step("no")
    assert decision == {"kind": "update", "state": before, "prompt_to_user": None}
    assert engine.state == before


def test_pending_confirmation_precedence_and_resolution() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")
    first = engine.step("use kubectl instead of docker")

    # While pending, directive parsing is suspended.
    second = engine.step("use docker")
    assert second == first
    assert engine.state["policies"] == {"docker": "use", "kubectl": "prohibit"}

    third = engine.step("yes")
    assert third["kind"] == "update"
    assert engine.state["policies"] == {"kubectl": "use"}


def test_pending_confirmation_suspends_admin_commands_until_resolved() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")
    first = engine.step("use kubectl instead of docker")
    before = engine.state

    assert engine.step("clear state") == first
    assert engine.step("reset policies") == first
    assert engine.state == before

    resolved = engine.step("yes")
    assert resolved["kind"] == "update"
    assert engine.state["policies"] == {"kubectl": "use"}


def test_pending_negative_discards_proposed_event() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")
    engine.step("use kubectl instead of docker")
    before = engine.state

    decision = engine.step("no")

    assert decision == {"kind": "update", "state": before, "prompt_to_user": None}
    assert engine.state["policies"] == {"docker": "use", "kubectl": "prohibit"}


def test_pending_confirmation_token_normalization() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")
    engine.step("use kubectl instead of docker")

    decision = engine.step("  YES!!!  ")
    assert decision["kind"] == "update"
    assert engine.state["policies"] == {"kubectl": "use"}


def test_pending_affirmative_confirmation_token_variants_are_accepted() -> None:
    for token in ["yes please", "Yep", "yeah", "ok", "  OKAY...  ", "sure!"]:
        engine = create_engine()
        engine.step("use docker")
        engine.step("prohibit kubectl")
        engine.step("use kubectl instead of docker")
        decision = engine.step(token)
        assert decision["kind"] == "update"
        assert engine.state["policies"] == {"kubectl": "use"}


def test_pending_negative_confirmation_token_normalization_no_punctuation() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")
    engine.step("use kubectl instead of docker")
    before = engine.state

    decision = engine.step("  NO!!!  ")
    assert decision == {"kind": "update", "state": before, "prompt_to_user": None}
    assert engine.state == before


def test_pending_negative_confirmation_token_normalization_no_thanks() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")
    engine.step("use kubectl instead of docker")
    before = engine.state

    decision = engine.step("no thanks.")
    assert decision == {"kind": "update", "state": before, "prompt_to_user": None}
    assert engine.state == before


def test_pending_negative_confirmation_token_variants_are_accepted() -> None:
    for token in ["nope", "Nope??", " no ", "NO THANKS!"]:
        engine = create_engine()
        engine.step("use docker")
        engine.step("prohibit kubectl")
        engine.step("use kubectl instead of docker")
        before = engine.state
        decision = engine.step(token)
        assert decision == {"kind": "update", "state": before, "prompt_to_user": None}
        assert engine.state == before


def test_pending_unmatched_input_remains_clarify_without_mutation() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")
    first = engine.step("use kubectl instead of docker")
    before = engine.state

    second = engine.step("maybe")
    assert second == first
    assert engine.state == before


def test_pending_unmatched_input_can_repeat_without_mutation() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")
    first = engine.step("use kubectl instead of docker")
    before = engine.state

    assert engine.step("later") == first
    assert engine.step("still later") == first
    assert engine.state == before


def test_replacement_pending_yes_can_override_conflicting_target_polarity() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")

    first = engine.step("use kubectl instead of docker")
    assert first["kind"] == "clarify"
    assert engine.state["policies"] == {"docker": "use", "kubectl": "prohibit"}

    second = engine.step("yes")
    assert second["kind"] == "update"
    assert engine.state["policies"] == {"kubectl": "use"}


def test_import_json_clears_pending_clarification_yes_no_not_confirmation() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")
    first = engine.step("use kubectl instead of docker")
    assert first["kind"] == "clarify"

    imported = {"premise": "baseline", "policies": {"pytest": "use"}, "version": 2}
    engine.import_json(json.dumps(imported))

    yes_decision = engine.step("yes")
    assert yes_decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == imported

    no_decision = engine.step("no")
    assert no_decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}


def test_remove_policy_uses_normalized_item_matching() -> None:
    engine = create_engine()
    engine.step("use The Docker")

    decision = engine.step("remove policy the docker")
    assert decision["kind"] == "update"
    assert engine.state == {"premise": None, "policies": {}, "version": 2}


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
