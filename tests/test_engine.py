import json

import pytest

from context_compiler import create_engine, get_policy_items, get_premise_value
from context_compiler.engine import (
    Action,
    DecisionKind,
    Engine,
    _contains_compound_directive,
    _match_canonical_directive_start,
    _normalize_confirmation,
    _parse_directive,
)

pytestmark = pytest.mark.contract

COMPOUND_DIRECTIVE_PROMPT = (
    "Multiple directives are not supported in one input.\nSubmit each directive separately."
)


def test_decision_kind_strenum_behavior() -> None:
    for kind in DecisionKind:
        assert kind == kind.value
        assert str(kind) == kind.value
        assert DecisionKind(kind.value) is kind


def test_parse_directive_delegates_canonical_kinds_to_existing_actions() -> None:
    assert _parse_directive("set premise concise replies") == Action(
        kind="set_premise", value="concise replies"
    )
    assert _parse_directive("change premise to concise replies") == Action(
        kind="change_premise", value="concise replies"
    )
    assert _parse_directive("use docker") == Action(kind="use_item", item="docker")
    assert _parse_directive("prohibit peanuts") == Action(kind="prohibit_item", item="peanuts")
    assert _parse_directive("remove policy docker") == Action(
        kind="remove_policy_item", item="docker"
    )
    assert _parse_directive("use podman instead of docker") == Action(
        kind="replace_use", new_item="podman", old_item="docker"
    )
    assert _parse_directive("clear premise") == Action(kind="clear_premise")
    assert _parse_directive("reset policies") == Action(kind="reset_policies")
    assert _parse_directive("clear state") == Action(kind="clear_state")


def test_parse_directive_returns_none_for_invalid_syntax_and_passthrough_inputs() -> None:
    assert _parse_directive("set premise") is None
    assert _parse_directive("change premise to") is None
    assert _parse_directive("use") is None
    assert _parse_directive("prohibit") is None
    assert _parse_directive("remove policy") is None
    assert _parse_directive("use instead of docker") is None
    assert _parse_directive("use docker and prohibit peanuts") is None
    assert _parse_directive("hello there") is None


def test_pre_mutation_clarify_legacy_invalid_action_branches_remain_stable() -> None:
    engine = create_engine()

    assert engine._pre_mutation_clarify(Action(kind="compound_directive_invalid")) == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": COMPOUND_DIRECTIVE_PROMPT,
    }
    assert engine._pre_mutation_clarify(Action(kind="set_premise", value="")) == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": (
            "Premise value cannot be empty.\nUse 'set premise <value>' with a non-empty value."
        ),
    }
    assert engine._pre_mutation_clarify(Action(kind="change_premise", value="")) == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": (
            "Premise value cannot be empty.\n"
            "Use 'change premise to <value>' with a non-empty value."
        ),
    }
    assert engine._pre_mutation_clarify(Action(kind="remove_policy_item", item="")) == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": (
            "Policy item cannot be empty.\nUse 'remove policy <item>' with a non-empty value."
        ),
    }
    assert engine._pre_mutation_clarify(Action(kind="use_item", item="")) == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": "Policy item cannot be empty.\nUse 'use <item>' with a non-empty value.",
    }
    assert engine._pre_mutation_clarify(Action(kind="prohibit_item", item="")) == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": (
            "Policy item cannot be empty.\nUse 'prohibit <item>' with a non-empty value."
        ),
    }
    assert engine._pre_mutation_clarify(Action(kind="replace_use_incomplete")) == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": (
            "Replacement requires both new and old items.\n"
            "Use 'use <new item> instead of <old item>' with non-empty values."
        ),
    }


def test_legacy_compound_detection_helpers_remain_unchanged() -> None:
    assert _contains_compound_directive("use docker and prohibit peanuts") is True
    assert _contains_compound_directive("hello there") is False
    assert _contains_compound_directive("use docker") is False
    assert _match_canonical_directive_start("use docker", -1) is None
    assert _match_canonical_directive_start("use docker", len("use docker")) is None
    assert _match_canonical_directive_start("abuse docker", 1) is None
    assert _match_canonical_directive_start("use", 0) == len("use")
    assert _match_canonical_directive_start("use docker", 0) == len("use")
    assert _match_canonical_directive_start("clear premise!", 0) == len("clear premise")


def test_initial_state_and_helpers() -> None:
    engine = create_engine()
    assert engine.state == {"premise": None, "policies": {}, "version": 2}
    assert engine.has_pending_clarification() is False
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


def test_import_json_rejects_empty_normalized_key_atomically() -> None:
    engine = create_engine()
    engine.step("use kubectl")
    before = engine.state

    with pytest.raises(ValueError, match="Invalid state payload"):
        engine.import_json(
            json.dumps(
                {
                    "premise": None,
                    "policies": {"Docker": "use", "a": "use"},
                    "version": 2,
                }
            )
        )

    assert engine.state == before


def test_import_json_accepts_valid_policy_key_and_normalizes_it() -> None:
    engine = create_engine()

    engine.import_json(
        json.dumps(
            {
                "premise": None,
                "policies": {"Docker": "use"},
                "version": 2,
            }
        )
    )

    assert engine.state == {"premise": None, "policies": {"docker": "use"}, "version": 2}


def test_has_pending_clarification_remains_false_after_invalid_replacement_followup() -> None:
    engine = create_engine()
    decision = engine.step("use kubectl instead of docker")
    assert decision["kind"] == "update"
    assert engine.has_pending_clarification() is False

    no_decision = engine.step("no")
    assert no_decision["kind"] == "passthrough"
    assert engine.has_pending_clarification() is False


def test_normalize_confirmation_collapses_unicode_spacing_and_trailing_punctuation() -> None:
    assert _normalize_confirmation("  YES!!  ") == "yes"
    assert _normalize_confirmation("No\t\tthanks...\n") == "no thanks"


def test_has_pending_clarification_stays_false_after_import_json() -> None:
    engine = create_engine()
    clarify = engine.step("use kubectl instead of docker")
    assert clarify["kind"] == "update"
    assert engine.has_pending_clarification() is False

    engine.import_json('{"policies":{},"premise":null,"version":2}')

    assert engine.has_pending_clarification() is False


def test_replace_use_clarifies_when_old_policy_is_not_use_in_invalid_internal_state() -> None:
    engine = create_engine()
    # Defensive-path coverage for impossible external state values.
    engine._state["policies"]["docker"] = "invalid"  # type: ignore[assignment]

    decision = engine.step("use kubectl instead of docker")

    assert decision == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": (
            "\"docker\" is not currently in use.\nReplacement requires an active 'use' policy."
        ),
    }


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
    ]:
        decision = engine.step(text)
        assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}

    assert engine.state == before


def test_lexical_normalization_accepts_canonical_directives() -> None:
    engine = create_engine()

    assert engine.step("clear premise ")["kind"] == "update"
    assert engine.step(" reset policies")["kind"] == "update"
    assert engine.step("clear state\t")["kind"] == "update"
    assert engine.step("Use docker")["kind"] == "update"
    assert engine.step("use\tdocker")["kind"] == "update"
    assert engine.step(" prohibit docker")["kind"] == "clarify"


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
    assert d2 == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": ("Premise already set.\nUse 'change premise to <value>' to modify it."),
    }
    assert engine.state == before


def test_set_premise_empty_payload_remains_passthrough() -> None:
    engine = create_engine()
    before = engine.state
    d1 = engine.step("set premise")
    assert d1 == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == before


def test_set_premise_whitespace_payload_remains_passthrough() -> None:
    engine = create_engine()
    before = engine.state
    d1 = engine.step("set premise    ")
    assert d1 == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == before


def test_set_premise_to_variant_remains_passthrough() -> None:
    engine = create_engine()

    decision = engine.step("set premise to concise replies")
    assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == {"premise": None, "policies": {}, "version": 2}


def test_set_premise_to_with_whitespace_payload_remains_passthrough() -> None:
    engine = create_engine()

    decision = engine.step("set premise to   ")

    assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == {"premise": None, "policies": {}, "version": 2}


def test_change_premise_requires_existing_premise() -> None:
    engine = create_engine()

    d1 = engine.step("change premise to concise")
    assert d1 == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": "No premise is set.\nUse 'set premise <value>' to define one.",
    }
    assert engine.state == {"premise": None, "policies": {}, "version": 2}

    engine.step("set premise first")
    d2 = engine.step("change premise to second")
    assert d2["kind"] == "update"
    assert engine.state["premise"] == "second"


def test_change_premise_to_empty_payload_remains_passthrough() -> None:
    engine = create_engine()
    engine.step("set premise baseline")
    before = engine.state

    d1 = engine.step("change premise to")
    assert d1 == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == before


def test_change_premise_to_without_space_payload_and_empty_variant_remain_passthrough() -> None:
    engine = create_engine()
    engine.step("set premise baseline")
    before = engine.state

    near_miss = engine.step("change premise baseline")
    assert near_miss == {"kind": "passthrough", "state": None, "prompt_to_user": None}

    decision = engine.step("change premise to")
    assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == before


def test_change_premise_to_whitespace_payload_remains_passthrough() -> None:
    engine = create_engine()
    engine.step("set premise baseline")
    before = engine.state

    d1 = engine.step("change premise to    ")
    assert d1 == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == before


def test_change_premise_missing_to_variant_is_passthrough() -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step("change premise concise replies")
    assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == before


def test_change_premise_with_whitespace_after_prefix_remains_passthrough() -> None:
    engine = create_engine(state={"premise": "baseline", "policies": {}, "version": 2})

    decision = engine.step("change premise   ")

    assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == {"premise": "baseline", "policies": {}, "version": 2}


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
        '"docker" is currently in use.\nRemove or replace it before prohibiting it.'
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
        '"docker" is currently prohibited.\nRemove or replace it before using it.'
    )
    assert engine2.state["policies"] == {"docker": "prohibit"}


def test_use_empty_payload_remains_passthrough() -> None:
    engine = create_engine()
    before = engine.state

    for text in ["use", "use ", "use    "]:
        decision = engine.step(text)
        assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
        assert engine.state == before


def test_prohibit_empty_payload_remains_passthrough() -> None:
    engine = create_engine()
    before = engine.state

    for text in ["prohibit", "prohibit ", "prohibit    "]:
        decision = engine.step(text)
        assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
        assert engine.state == before


def test_replace_use_incomplete_payload_remains_passthrough() -> None:
    engine = create_engine()
    before = engine.state

    for text in [
        "use x instead of",
        "use x instead of ",
        "use  instead of y",
        "use   instead of y",
        "use instead of y",
    ]:
        decision = engine.step(text)
        assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
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


def test_remove_policy_empty_payload_remains_passthrough() -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step("remove policy")

    assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == before


def test_remove_policy_whitespace_payload_remains_passthrough() -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step("remove policy    ")

    assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
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


def test_replace_use_missing_source_applies_as_use_update_without_pending() -> None:
    engine = create_engine()

    d1 = engine.step("use kubectl instead of docker")
    assert d1 == {
        "kind": "update",
        "state": {"premise": None, "policies": {"kubectl": "use"}, "version": 2},
        "prompt_to_user": None,
    }
    assert engine.state == {"premise": None, "policies": {"kubectl": "use"}, "version": 2}
    assert engine.has_pending_clarification() is False


def test_replace_use_missing_source_yes_confirmation_is_passthrough() -> None:
    engine = create_engine()

    first = engine.step("use kubectl instead of docker")
    assert first == {
        "kind": "update",
        "state": {"premise": None, "policies": {"kubectl": "use"}, "version": 2},
        "prompt_to_user": None,
    }
    assert engine.state == {"premise": None, "policies": {"kubectl": "use"}, "version": 2}

    second = engine.step("yes")
    assert second == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == {"premise": None, "policies": {"kubectl": "use"}, "version": 2}


def test_replace_use_missing_source_no_confirmation_has_no_mutation() -> None:
    engine = create_engine()
    engine.step("use kubectl instead of docker")
    before = engine.state

    decision = engine.step("no")
    assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == before


def test_replace_use_missing_source_still_reports_target_prohibit_when_new_item_prohibited() -> (
    None
):
    engine = create_engine()
    engine.step("prohibit kubectl")

    decision = engine.step("use kubectl instead of docker")
    assert decision == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": (
            '"kubectl" is currently prohibited.\n'
            "Submit explicit directive(s) to remove it or use a different item."
        ),
    }


def test_replace_use_missing_source_ignores_unrelated_existing_policies() -> None:
    engine = create_engine()
    engine.step("use python and docker")

    decision = engine.step("use kubectl instead of python")
    assert decision["kind"] == "update"
    assert engine.state["policies"] == {"kubectl": "use", "python and docker": "use"}


def test_replace_use_missing_source_ignores_other_conflicting_entries() -> None:
    engine = create_engine()
    engine.step("use python and docker")
    engine.step("prohibit python tooling")

    decision = engine.step("use kubectl instead of python")
    assert decision["kind"] == "update"
    assert engine.state["policies"] == {
        "kubectl": "use",
        "python and docker": "use",
        "python tooling": "prohibit",
    }


def test_replace_use_missing_source_with_empty_probe_uses_invalid_prompt() -> None:
    engine = create_engine()
    engine.step("use python and docker")

    decision = engine.step("use kubectl instead of the")
    assert decision["kind"] == "update"
    assert engine.state == {
        "premise": None,
        "policies": {"kubectl": "use", "python and docker": "use"},
        "version": 2,
    }


def test_replace_use_ky_prohibit_returns_non_pending_clarify() -> None:
    engine = create_engine()
    engine.step("prohibit docker")
    engine.step("use pytest")

    first = engine.step("use kubectl instead of docker")
    expected = (
        '"docker" is currently prohibited.\n'
        "Submit explicit directive(s) to remove it or use a different item."
    )
    assert first == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": expected,
    }
    assert engine.state["policies"] == {"docker": "prohibit", "pytest": "use"}

    assert engine.has_pending_clarification() is False


def test_replace_use_ky_prohibit_yes_does_not_authorize_mutation() -> None:
    engine = create_engine()
    engine.step("prohibit docker")
    engine.step("use pytest")
    first = engine.step("use kubectl instead of docker")
    before = engine.state

    assert first["kind"] == "clarify"
    decision = engine.step("yes")
    assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == before


def test_replace_use_kx_prohibit_returns_non_pending_clarify() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")

    first = engine.step("use kubectl instead of docker")
    expected = (
        '"kubectl" is currently prohibited.\n'
        "Submit explicit directive(s) to remove it or use a different item."
    )
    assert first == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": expected,
    }
    assert engine.state["policies"] == {"docker": "use", "kubectl": "prohibit"}

    assert engine.has_pending_clarification() is False


def test_replace_use_priority_prefers_source_prohibit_clarify_when_both_prohibit() -> None:
    engine = create_engine()
    engine.step("prohibit docker")
    engine.step("prohibit kubectl")

    first = engine.step("use kubectl instead of docker")
    expected = (
        '"docker" is currently prohibited.\n'
        "Submit explicit directive(s) to remove it or use a different item."
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
            '"docker" is currently prohibited.\n'
            "Submit explicit directive(s) to remove it or use a different item."
        ),
    }
    assert engine.state == before


def test_replace_use_kx_prohibit_no_confirmation_has_no_mutation() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")
    first = engine.step("use kubectl instead of docker")
    before = engine.state

    assert first["kind"] == "clarify"
    decision = engine.step("no")
    assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == before


def test_missing_source_replacement_does_not_block_following_directives() -> None:
    engine = create_engine()
    first = engine.step("use kubectl instead of docker")
    assert first["kind"] == "update"

    second = engine.step("use docker")
    assert second["kind"] == "update"
    assert engine.state["policies"] == {"docker": "use", "kubectl": "use"}

    third = engine.step("yes")
    assert third == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state["policies"] == {"docker": "use", "kubectl": "use"}


def test_missing_source_replacement_does_not_suspend_admin_commands() -> None:
    engine = create_engine()
    engine.step("use kubectl instead of docker")
    before = {"premise": None, "policies": {"kubectl": "use"}, "version": 2}

    assert engine.state == before

    assert engine.step("clear state")["kind"] == "update"
    assert engine.step("reset policies")["kind"] == "update"
    assert engine.state == {"premise": None, "policies": {}, "version": 2}

    resolved = engine.step("yes")
    assert resolved == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state["policies"] == {}


def test_missing_source_replacement_negative_followup_is_passthrough() -> None:
    engine = create_engine()
    engine.step("use kubectl instead of docker")

    decision = engine.step("no")

    assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state["policies"] == {"kubectl": "use"}


def test_missing_source_replacement_confirmation_tokens_are_not_consumed() -> None:
    engine = create_engine()
    engine.step("use kubectl instead of docker")

    decision = engine.step("  YES!!!  ")
    assert decision["kind"] == "passthrough"
    assert engine.state["policies"] == {"kubectl": "use"}


def test_missing_source_replacement_affirmative_token_variants_are_passthrough() -> None:
    for token in ["yes please", "Yep", "yeah", "ok", "  OKAY...  ", "sure!"]:
        engine = create_engine()
        engine.step("use kubectl instead of docker")
        decision = engine.step(token)
        assert decision["kind"] == "passthrough"
        assert engine.state["policies"] == {"kubectl": "use"}


def test_missing_source_replacement_negative_tokens_are_passthrough() -> None:
    engine = create_engine()
    engine.step("use kubectl instead of docker")
    before = engine.state

    decision = engine.step("  NO!!!  ")
    assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == before


def test_missing_source_replacement_no_thanks_is_passthrough() -> None:
    engine = create_engine()
    engine.step("use kubectl instead of docker")
    before = engine.state

    decision = engine.step("no thanks.")
    assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == before


def test_missing_source_replacement_negative_token_variants_are_passthrough() -> None:
    for token in ["nope", "Nope??", " no ", "NO THANKS!"]:
        engine = create_engine()
        engine.step("use kubectl instead of docker")
        before = engine.state
        decision = engine.step(token)
        assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
        assert engine.state == before


def test_missing_source_replacement_unmatched_followup_is_passthrough() -> None:
    engine = create_engine()
    engine.step("use kubectl instead of docker")
    before = engine.state

    second = engine.step("maybe")
    assert second == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == before


def test_missing_source_replacement_unmatched_followups_remain_passthrough() -> None:
    engine = create_engine()
    engine.step("use kubectl instead of docker")
    before = engine.state

    assert engine.step("later") == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.step("still later") == {
        "kind": "passthrough",
        "state": None,
        "prompt_to_user": None,
    }
    assert engine.state == before


def test_prohibited_replacement_yes_cannot_override_conflicting_target_polarity() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")

    first = engine.step("use kubectl instead of docker")
    assert first["kind"] == "clarify"
    assert engine.state["policies"] == {"docker": "use", "kubectl": "prohibit"}

    second = engine.step("yes")
    assert second["kind"] == "passthrough"
    assert engine.state["policies"] == {"docker": "use", "kubectl": "prohibit"}


def test_import_json_clears_pending_clarification_yes_no_not_confirmation() -> None:
    engine = create_engine()
    first = engine.step("use kubectl instead of docker")
    assert first["kind"] == "update"

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


@pytest.mark.parametrize(
    ("user_input", "initial_state"),
    [
        ("use docker and prohibit peanuts", {"premise": None, "policies": {}, "version": 2}),
        ("use docker or prohibit peanuts", {"premise": None, "policies": {}, "version": 2}),
        ("use docker xor prohibit peanuts", {"premise": None, "policies": {}, "version": 2}),
        ("use docker but prohibit peanuts", {"premise": None, "policies": {}, "version": 2}),
        ("use docker; prohibit peanuts", {"premise": None, "policies": {}, "version": 2}),
        ("use docker. prohibit peanuts", {"premise": None, "policies": {}, "version": 2}),
        (
            "use docker for development and prohibit peanuts",
            {"premise": None, "policies": {}, "version": 2},
        ),
        (
            "set premise vegetarian curry and prohibit peanuts",
            {"premise": None, "policies": {}, "version": 2},
        ),
        (
            "change premise to vegan curry or use docker",
            {"premise": "baseline", "policies": {}, "version": 2},
        ),
        (
            "remove policy docker and use podman",
            {"premise": None, "policies": {"docker": "use"}, "version": 2},
        ),
        (
            "clear premise and prohibit peanuts",
            {"premise": "baseline", "policies": {}, "version": 2},
        ),
        (
            "reset policies; use docker",
            {"premise": None, "policies": {"docker": "prohibit"}, "version": 2},
        ),
        (
            "clear state then set premise new project",
            {"premise": "baseline", "policies": {"docker": "use"}, "version": 2},
        ),
        (
            'use "docker and prohibit peanuts"',
            {"premise": None, "policies": {}, "version": 2},
        ),
        (
            'set premise "use docker and prohibit peanuts"',
            {"premise": None, "policies": {}, "version": 2},
        ),
        (
            "use docker instead of prohibit peanuts",
            {"premise": None, "policies": {}, "version": 2},
        ),
    ],
)
def test_compound_directives_remain_passthrough_without_mutation(
    user_input: str, initial_state: dict[str, object]
) -> None:
    engine = create_engine(state=initial_state)
    before = engine.state

    decision = engine.step(user_input)

    assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == before
    assert engine.has_pending_clarification() is False


def test_quoted_non_directive_leading_input_remains_passthrough() -> None:
    engine = create_engine()

    decision = engine.step('"use docker and prohibit peanuts"')

    assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == {"premise": None, "policies": {}, "version": 2}
    assert engine.has_pending_clarification() is False


@pytest.mark.parametrize(
    ("user_input", "initial_state", "expected_decision_kind", "expected_state"),
    [
        (
            "use docker for prohibitively expensive builds",
            {"premise": None, "policies": {}, "version": 2},
            "update",
            {
                "premise": None,
                "policies": {"docker for prohibitively expensive builds": "use"},
                "version": 2,
            },
        ),
        (
            "set premise reusable docker-prohibit-safe workflow",
            {"premise": None, "policies": {}, "version": 2},
            "update",
            {"premise": "reusable docker-prohibit-safe workflow", "policies": {}, "version": 2},
        ),
        (
            "change premise to reset policieset ownership",
            {"premise": "baseline", "policies": {}, "version": 2},
            "update",
            {"premise": "reset policieset ownership", "policies": {}, "version": 2},
        ),
        (
            "remove policy clear stateful systems",
            {"premise": None, "policies": {"docker": "use"}, "version": 2},
            "update",
            {"premise": None, "policies": {"docker": "use"}, "version": 2},
        ),
    ],
)
def test_directive_like_substrings_inside_larger_words_do_not_trigger_compound_rejection(
    user_input: str,
    initial_state: dict[str, object],
    expected_decision_kind: str,
    expected_state: dict[str, object],
) -> None:
    engine = create_engine(state=initial_state)

    decision = engine.step(user_input)

    assert not (
        decision["kind"] == "clarify" and decision["prompt_to_user"] == COMPOUND_DIRECTIVE_PROMPT
    )
    assert decision["kind"] == expected_decision_kind
    assert engine.state == expected_state
    assert engine.has_pending_clarification() is False


@pytest.mark.parametrize(
    ("user_input", "initial_state", "expected_state"),
    [
        (
            "use docker",
            {"premise": None, "policies": {}, "version": 2},
            {"premise": None, "policies": {"docker": "use"}, "version": 2},
        ),
        (
            "prohibit peanuts",
            {"premise": None, "policies": {}, "version": 2},
            {"premise": None, "policies": {"peanuts": "prohibit"}, "version": 2},
        ),
        (
            "set premise vegetarian curry",
            {"premise": None, "policies": {}, "version": 2},
            {"premise": "vegetarian curry", "policies": {}, "version": 2},
        ),
        (
            "change premise to vegan curry",
            {"premise": "vegetarian curry", "policies": {}, "version": 2},
            {"premise": "vegan curry", "policies": {}, "version": 2},
        ),
        (
            "remove policy docker",
            {"premise": None, "policies": {"docker": "use"}, "version": 2},
            {"premise": None, "policies": {}, "version": 2},
        ),
        (
            "clear premise",
            {"premise": "vegetarian curry", "policies": {}, "version": 2},
            {"premise": None, "policies": {}, "version": 2},
        ),
        (
            "reset policies",
            {"premise": None, "policies": {"docker": "use"}, "version": 2},
            {"premise": None, "policies": {}, "version": 2},
        ),
        (
            "clear state",
            {"premise": "baseline", "policies": {"docker": "use"}, "version": 2},
            {"premise": None, "policies": {}, "version": 2},
        ),
        (
            "use docker instead of podman",
            {"premise": None, "policies": {"podman": "use"}, "version": 2},
            {"premise": None, "policies": {"docker": "use"}, "version": 2},
        ),
    ],
)
def test_valid_single_directives_still_work(
    user_input: str, initial_state: dict[str, object], expected_state: dict[str, object]
) -> None:
    engine = create_engine(state=initial_state)

    decision = engine.step(user_input)

    assert decision == {"kind": "update", "state": expected_state, "prompt_to_user": None}
    assert engine.state == expected_state
    assert engine.has_pending_clarification() is False


@pytest.mark.parametrize(
    "directive_start",
    [
        "set premise vegetarian curry",
        "change premise to vegan curry",
        "use docker",
        "prohibit peanuts",
        "remove policy docker",
        "use docker instead of podman",
        "clear premise",
        "reset policies",
        "clear state",
    ],
)
def test_all_canonical_directive_starts_remain_single_directive_when_valid(
    directive_start: str,
) -> None:
    engine = create_engine(
        state={"premise": "baseline", "policies": {"podman": "use"}, "version": 2}
    )

    decision = engine.step(directive_start)

    assert not (
        decision["kind"] == "clarify" and decision["prompt_to_user"] == COMPOUND_DIRECTIVE_PROMPT
    )


def test_compound_passthrough_after_prior_missing_source_replacement_update() -> None:
    engine = create_engine()
    first = engine.step("use kubectl instead of docker")
    assert first == {
        "kind": "update",
        "state": {"premise": None, "policies": {"kubectl": "use"}, "version": 2},
        "prompt_to_user": None,
    }
    assert engine.has_pending_clarification() is False

    decision = engine.step("use docker and prohibit peanuts")

    assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == {"premise": None, "policies": {"kubectl": "use"}, "version": 2}
    assert engine.has_pending_clarification() is False


def test_constructor_with_state_initializes_from_valid_state() -> None:
    state = {"premise": "Prefer bullets", "policies": {"pytest": "use"}, "version": 2}
    engine = Engine(state=state)
    assert engine.state == state
