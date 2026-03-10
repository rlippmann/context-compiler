import json

import pytest

from context_compiler import create_engine
from context_compiler.engine import DecisionKind, Engine


def test_decision_kind_strenum_behavior() -> None:
    for kind in DecisionKind:
        assert kind == kind.value
        assert str(kind) == kind.value
        assert DecisionKind(kind.value) is kind


def test_state_getter_returns_defensive_copy() -> None:
    engine = create_engine()
    snapshot = engine.state
    snapshot["facts"]["focus.primary"] = "mutated"
    assert engine.state["facts"]["focus.primary"] is None


def test_export_json_returns_complete_representation_of_state() -> None:
    engine = create_engine()
    engine.step("use Nord Stage 4")
    engine.step("don't use docker")

    payload = engine.export_json()
    assert json.loads(payload) == {
        "facts": {"focus.primary": "Nord Stage 4"},
        "policies": {"prohibit": ["docker"]},
        "version": 1,
    }


def test_import_json_restores_state_exactly() -> None:
    engine = create_engine()
    engine.step("use Nord Stage 4")
    engine.step("don't use docker")
    snapshot = engine.export_json()

    engine.step("clear state")
    engine.import_json(snapshot)

    assert engine.state == {
        "facts": {"focus.primary": "Nord Stage 4"},
        "policies": {"prohibit": ["docker"]},
        "version": 1,
    }


def test_export_import_round_trip_preserves_state() -> None:
    source = create_engine()
    source.step("use Nord Stage 4")
    source.step("don't use docker")

    target = create_engine()
    target.import_json(source.export_json())

    assert target.state == source.state


def test_imported_state_matches_live_subsequent_behavior() -> None:
    live = create_engine()
    live.step("use Nord Stage 4")
    live.step("don't use parallel octaves")

    imported = create_engine()
    imported.import_json(live.export_json())

    turns = [
        "actually Nord Stage 3",
        "don't use voice crossing",
        "reset policies",
        "allow docker",
    ]
    for turn in turns:
        assert imported.step(turn) == live.step(turn)
        assert imported.state == live.state


def test_import_json_invalid_json_and_unsupported_version_are_rejected() -> None:
    engine = create_engine()

    try:
        engine.import_json("{")
        raise AssertionError("expected ValueError for invalid JSON")
    except ValueError as exc:
        assert "Invalid JSON payload" in str(exc)

    try:
        engine.import_json(
            json.dumps(
                {
                    "facts": {"focus.primary": None},
                    "policies": {"prohibit": []},
                    "version": 2,
                }
            )
        )
        raise AssertionError("expected ValueError for unsupported version")
    except ValueError as exc:
        assert "Unsupported state version" in str(exc)


@pytest.mark.parametrize(
    "payload",
    [
        {"facts": {}, "policies": {"prohibit": []}, "version": 1},
        {"facts": {"focus.primary": None}, "policies": {"prohibit": "docker"}, "version": 1},
        {"facts": {"focus.primary": 123}, "policies": {"prohibit": []}, "version": 1},
    ],
)
def test_import_json_rejects_structurally_invalid_payload(payload: dict[str, object]) -> None:
    engine = create_engine()
    with pytest.raises(ValueError):
        engine.import_json(json.dumps(payload))


def test_import_json_canonicalizes_duplicate_unsorted_prohibit_values() -> None:
    engine = create_engine()
    engine.import_json(
        json.dumps(
            {
                "facts": {"focus.primary": None},
                "policies": {"prohibit": ["kubernetes", "docker", "docker"]},
                "version": 1,
            }
        )
    )

    assert engine.state == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": ["docker", "kubernetes"]},
        "version": 1,
    }


def test_import_json_sanitizes_fact_value_like_live_fact_write() -> None:
    engine = create_engine()
    engine.import_json(
        json.dumps(
            {
                "facts": {"focus.primary": "  MacBook   M3`  "},
                "policies": {"prohibit": []},
                "version": 1,
            }
        )
    )

    assert engine.state["facts"]["focus.primary"] == "MacBook M3'"


def test_constructor_with_state_initializes_from_normalized_state() -> None:
    raw_state = {
        "facts": {"focus.primary": "  MacBook   M3`  "},
        "policies": {"prohibit": ["kubernetes", "docker", "docker"]},
        "version": 1,
    }
    loaded_state = json.loads(json.dumps(raw_state))

    constructed = Engine(state=loaded_state)

    assert constructed.state == {
        "facts": {"focus.primary": "MacBook M3'"},
        "policies": {"prohibit": ["docker", "kubernetes"]},
        "version": 1,
    }


def test_create_engine_with_state_initializes_from_normalized_state() -> None:
    created = create_engine(
        state={
            "facts": {"focus.primary": "  MacBook   M3`  "},
            "policies": {"prohibit": ["kubernetes", "docker", "docker"]},
            "version": 1,
        }
    )

    assert created.state == {
        "facts": {"focus.primary": "MacBook M3'"},
        "policies": {"prohibit": ["docker", "kubernetes"]},
        "version": 1,
    }


@pytest.mark.parametrize(
    ("path", "bad_state"),
    [
        (
            "constructor",
            {
                "facts": {"focus.primary": None},
                "policies": {"prohibit": []},
            },
        ),
        (
            "setter",
            {
                "facts": {"focus.primary": None},
                "policies": {"prohibit": "docker"},
                "version": 1,
            },
        ),
    ],
)
def test_object_state_replacement_paths_reject_invalid_state(path: str, bad_state: object) -> None:
    if path == "constructor":
        with pytest.raises(ValueError):
            Engine(state=bad_state)
        return

    engine = create_engine()
    with pytest.raises(ValueError):
        engine.state = bad_state


def test_state_setter_replaces_state_and_clears_pending_clarification() -> None:
    engine = create_engine()
    decision = engine.step("no use docker")
    assert decision["kind"] == "clarify"

    engine.state = {
        "facts": {"focus.primary": "Nord Stage 4"},
        "policies": {"prohibit": ["kubernetes", "docker", "docker"]},
        "version": 1,
    }

    decision_after_setter = engine.step("yes")
    assert decision_after_setter["kind"] == "passthrough"
    assert engine.state == {
        "facts": {"focus.primary": "Nord Stage 4"},
        "policies": {"prohibit": ["docker", "kubernetes"]},
        "version": 1,
    }


def test_constructor_setter_and_import_json_share_normalization_behavior() -> None:
    raw_state = {
        "facts": {"focus.primary": "  MacBook   M3`  "},
        "policies": {"prohibit": ["kubernetes", "docker", "docker"]},
        "version": 1,
    }

    from_ctor = Engine(state=json.loads(json.dumps(raw_state)))

    from_setter = create_engine()
    from_setter.state = json.loads(json.dumps(raw_state))

    from_import = create_engine()
    from_import.import_json(json.dumps(raw_state))

    assert from_ctor.state == from_setter.state == from_import.state


def test_import_json_clears_pending_clarification_state() -> None:
    engine = create_engine()
    decision = engine.step("no use docker")
    assert decision["kind"] == "clarify"

    engine.import_json(
        json.dumps(
            {
                "facts": {"focus.primary": "Nord Stage 4"},
                "policies": {"prohibit": ["kubernetes"]},
                "version": 1,
            }
        )
    )

    decision_after_import = engine.step("yes")
    assert decision_after_import["kind"] == "passthrough"
    assert engine.state == {
        "facts": {"focus.primary": "Nord Stage 4"},
        "policies": {"prohibit": ["kubernetes"]},
        "version": 1,
    }


def test_imported_fact_state_restores_correction_behavior() -> None:
    engine = create_engine()
    engine.import_json(
        json.dumps(
            {
                "facts": {"focus.primary": "Nord Stage 4"},
                "policies": {"prohibit": []},
                "version": 1,
            }
        )
    )

    decision = engine.step("actually Nord Stage 3")
    assert decision["kind"] == "update"
    assert engine.state["facts"]["focus.primary"] == "Nord Stage 3"


def test_directive_parsing_positive_negative_and_allow() -> None:
    engine = create_engine()

    decision1 = engine.step("use Nord Stage 4")
    assert decision1["kind"] == "update"
    assert engine.state["facts"]["focus.primary"] == "Nord Stage 4"

    decision2 = engine.step("please don't use the parallel octaves and a voice crossing")
    assert decision2["kind"] == "update"
    assert engine.state["policies"]["prohibit"] == ["parallel octaves", "voice crossing"]

    decision3 = engine.step("allow voice crossing")
    assert decision3["kind"] == "update"
    assert engine.state["policies"]["prohibit"] == ["parallel octaves"]


def test_hard_negative_dont_use_stores_item_without_use_prefix() -> None:
    engine = create_engine()

    decision = engine.step("don't use docker")

    assert decision["kind"] == "update"
    assert engine.state["policies"]["prohibit"] == ["docker"]


def test_avoid_is_passthrough_and_does_not_mutate_state() -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step("avoid use docker")

    assert decision["kind"] == "passthrough"
    assert engine.state == before


def test_correction_replaces_most_recent_exclusive_fact() -> None:
    engine = create_engine()

    engine.step("I am using Nord Stage 3")
    decision = engine.step("actually Nord Stage 4")

    assert decision["kind"] == "update"
    assert engine.state["facts"]["focus.primary"] == "Nord Stage 4"


def test_please_use_directive_updates_fact() -> None:
    engine = create_engine()

    decision = engine.step("please use Nord Stage 4")

    assert decision["kind"] == "update"
    assert engine.state["facts"]["focus.primary"] == "Nord Stage 4"


def test_correction_without_prior_exclusive_fact_requires_clarification() -> None:
    engine = create_engine()

    decision = engine.step("correction: Nord Stage 4")

    assert decision["kind"] == "clarify"
    assert engine.state["facts"]["focus.primary"] is None


def test_policy_additions_are_sorted_unique_and_removal_is_noop_when_absent() -> None:
    engine = create_engine()

    engine.step("don't use voice crossing")
    engine.step("never the parallel octaves")
    decision = engine.step("do not voice crossing")

    assert decision["kind"] == "update"
    assert engine.state["policies"]["prohibit"] == ["parallel octaves", "voice crossing"]

    decision2 = engine.step("allow docker")
    assert decision2["kind"] == "update"
    assert engine.state["policies"]["prohibit"] == ["parallel octaves", "voice crossing"]


def test_ambiguity_returns_clarify_and_does_not_mutate() -> None:
    engine = create_engine()

    decision = engine.step("don use parallel octaves")

    assert decision["kind"] == "clarify"
    assert engine.state == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": []},
        "version": 1,
    }


def test_ambiguous_multi_item_directive_requires_clarification() -> None:
    engine = create_engine()

    decision = engine.step("no use docker and parallel octaves")

    assert decision["kind"] == "clarify"
    assert engine.state == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": []},
        "version": 1,
    }


def test_correction_does_not_bypass_pending_clarification() -> None:
    engine = create_engine()

    # create ambiguity
    decision1 = engine.step("no use docker")
    assert decision1["kind"] == "clarify"

    # attempt correction while pending
    decision2 = engine.step("actually don't use docker")

    assert decision2["kind"] == "clarify"
    assert engine.state == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": []},
        "version": 1,
    }


def test_yes_no_passthrough_without_pending_clarification() -> None:
    engine = create_engine()
    before = engine.state

    decision_yes = engine.step("yes")
    assert decision_yes["kind"] == "passthrough"
    assert engine.state == before

    decision_no = engine.step("no")
    assert decision_no["kind"] == "passthrough"
    assert engine.state == before


def test_pending_reprompts_on_non_yes_no() -> None:
    engine = create_engine()
    engine.step("no use docker")
    before = engine.state

    d = engine.step("maybe")
    assert d["kind"] == "clarify"
    assert engine.state == before


def test_ambiguous_policy_add_clarification_uses_expected_prompt_text() -> None:
    engine = create_engine()

    decision = engine.step("no use docker")

    assert decision["kind"] == "clarify"
    assert decision["prompt_to_user"] == "Did you mean to prohibit 'docker'?"


def test_pending_clarification_reprompt_keeps_state_unchanged() -> None:
    engine = create_engine()

    decision1 = engine.step("no use docker")
    assert decision1["kind"] == "clarify"
    before = engine.state

    decision2 = engine.step("proceed")
    assert decision2["kind"] == "clarify"
    assert engine.state == before


def test_pending_clarification_blocks_other_mutations_until_resolved() -> None:
    engine = create_engine()

    decision1 = engine.step("no use docker")
    assert decision1["kind"] == "clarify"

    decision2 = engine.step("use Nord Stage 4")
    assert decision2["kind"] == "clarify"
    assert engine.state["facts"]["focus.primary"] is None
    assert engine.state["policies"]["prohibit"] == []

    decision3 = engine.step("yes")
    assert decision3["kind"] == "update"
    assert engine.state["policies"]["prohibit"] == ["docker"]
    assert engine.state["facts"]["focus.primary"] is None


def test_reset_commands() -> None:
    engine = create_engine()

    engine.step("use Nord Stage 4")
    engine.step("don't use parallel octaves")

    decision1 = engine.step("reset policies")
    assert decision1["kind"] == "update"
    assert engine.state == {
        "facts": {"focus.primary": "Nord Stage 4"},
        "policies": {"prohibit": []},
        "version": 1,
    }

    engine.step("use Nord Stage 4")
    engine.step("don't use parallel octaves")

    decision_constraints = engine.step("clear constraints")
    assert decision_constraints["kind"] == "passthrough"
    assert engine.state == {
        "facts": {"focus.primary": "Nord Stage 4"},
        "policies": {"prohibit": ["parallel octaves"]},
        "version": 1,
    }

    engine.step("use Nord Stage 4")
    engine.step("don't use parallel octaves")

    decision2 = engine.step("clear state")
    assert decision2["kind"] == "update"
    assert engine.state == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": []},
        "version": 1,
    }


def test_passthrough_input_does_not_mutate_state() -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step("hello there")

    assert decision["kind"] == "passthrough"
    assert engine.state == before


def test_reset_policies_when_already_empty_preserves_existing_fact() -> None:
    engine = create_engine()

    engine.step("use Nord Stage 4")

    decision = engine.step("reset policies")

    assert decision["kind"] == "update"
    assert engine.state == {
        "facts": {"focus.primary": "Nord Stage 4"},
        "policies": {"prohibit": []},
        "version": 1,
    }


def test_reset_policies_keeps_last_exclusive_fact_correctable() -> None:
    engine = create_engine()

    engine.step("use Nord Stage 4")
    engine.step("don't use docker")
    engine.step("reset policies")

    decision = engine.step("actually Nord Stage 3")
    assert decision["kind"] == "update"
    assert engine.state["facts"]["focus.primary"] == "Nord Stage 3"


def test_reset_policies_on_initial_state_is_update_and_noop() -> None:
    engine = create_engine()

    decision = engine.step("reset policies")

    assert decision["kind"] == "update"
    assert engine.state == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": []},
        "version": 1,
    }


def test_unicode_apostrophe_positive_directive() -> None:
    engine = create_engine()

    decision = engine.step("i’m using Nord Stage 4")

    assert decision["kind"] == "update"
    assert engine.state["facts"]["focus.primary"] == "Nord Stage 4"


def test_unicode_apostrophe_negative_directive() -> None:
    engine = create_engine()

    decision = engine.step("don’t use docker")

    assert decision["kind"] == "update"
    assert engine.state["policies"]["prohibit"] == ["docker"]


def test_correction_with_empty_payload_clarifies() -> None:
    engine = create_engine()

    engine.step("use Nord Stage 3")
    decision = engine.step("actually   ")

    assert decision["kind"] == "clarify"


def test_correction_with_invalid_conjunction_clarifies() -> None:
    engine = create_engine()

    engine.step("use Nord Stage 3")
    decision = engine.step("actually and Nord")

    assert decision["kind"] == "clarify"


def test_allow_with_empty_payload_clarifies_without_mutating_state() -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step("allow   ")

    assert decision["kind"] == "clarify"
    assert engine.state == before


def test_use_with_unclear_payload_clarifies_without_mutating_state() -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step("use and")

    assert decision["kind"] == "clarify"
    assert engine.state == before


def test_pending_yes_with_whitespace_resolves() -> None:
    engine = create_engine()

    engine.step("no use docker")
    decision = engine.step("   yes   ")

    assert decision["kind"] == "update"
    assert engine.state["policies"]["prohibit"] == ["docker"]


def test_yes_after_non_pending_clarify_is_passthrough() -> None:
    engine = create_engine()

    decision1 = engine.step("no use docker and x")
    assert decision1["kind"] == "clarify"

    decision2 = engine.step("yes")

    assert decision2["kind"] == "passthrough"
    assert engine.state == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": []},
        "version": 1,
    }


def test_unicode_apostrophe_negative_directive_with_please() -> None:
    engine = create_engine()

    decision = engine.step("please don’t use docker")

    assert decision["kind"] == "update"
    assert engine.state["policies"]["prohibit"] == ["docker"]


def test_refrain_from_is_passthrough_and_does_not_mutate_state() -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step("refrain from use docker")

    assert decision["kind"] == "passthrough"
    assert engine.state == before


def test_hard_negative_dont_without_apostrophe_updates_policy() -> None:
    engine = create_engine()

    decision = engine.step("dont use docker")

    assert decision["kind"] == "update"
    assert engine.state["policies"]["prohibit"] == ["docker"]


def test_hard_negative_please_dont_without_apostrophe_updates_policy() -> None:
    engine = create_engine()

    decision = engine.step("please dont use docker")

    assert decision["kind"] == "update"
    assert engine.state["policies"]["prohibit"] == ["docker"]


def test_hard_negative_dont_without_use_still_adds_policy() -> None:
    engine = create_engine()

    decision = engine.step("dont docker")

    assert decision["kind"] == "update"
    assert engine.state["policies"]["prohibit"] == ["docker"]


def test_correction_with_multiple_values_clarifies_and_keeps_state() -> None:
    engine = create_engine()
    engine.step("use Nord Stage 4")
    before = engine.state

    decision = engine.step("actually macbook and linux")

    assert decision["kind"] == "clarify"
    assert engine.state == before


def test_empty_hard_negative_clarifies_with_prohibit_prompt() -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step("don't use")

    assert decision["kind"] == "clarify"
    assert decision["prompt_to_user"] == "What should I prohibit?"
    assert engine.state == before


def test_hard_positive_empty_payload_clarifies_with_use_prompt() -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step("use")

    assert decision["kind"] == "clarify"
    assert decision["prompt_to_user"] == "What should I use?"
    assert engine.state == before


def test_hard_positive_multi_value_payload_clarifies_with_single_value_prompt() -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step("use macbook and linux")

    assert decision["kind"] == "clarify"
    assert decision["prompt_to_user"] == "Please provide a single value to use."
    assert engine.state == before


def test_pending_clarification_rejected_by_explicit_no_is_passthrough() -> None:
    engine = create_engine()
    before = engine.state

    first = engine.step("no use docker")
    assert first["kind"] == "clarify"

    second = engine.step("no")
    assert second["kind"] == "passthrough"
    assert engine.state == before


@pytest.mark.parametrize(
    ("path", "bad_state"),
    [
        ("constructor", []),
        ("setter", "not-a-dict"),
        ("constructor", {"facts": [], "policies": {"prohibit": []}, "version": 1}),
        ("setter", {"facts": {"focus.primary": None}, "policies": [], "version": 1}),
        (
            "constructor",
            {"facts": {"focus.primary": 123}, "policies": {"prohibit": []}, "version": 1},
        ),
    ],
)
def test_object_state_paths_reject_malformed_state_inputs(path: str, bad_state: object) -> None:
    if path == "constructor":
        with pytest.raises(ValueError):
            Engine(state=bad_state)
        return

    engine = create_engine()
    with pytest.raises(ValueError):
        engine.state = bad_state


def test_allow_suffix_removes_existing_prohibition() -> None:
    engine = create_engine()
    engine.step("don't use docker")

    decision = engine.step("docker is fine")

    assert decision["kind"] == "update"
    assert engine.state["policies"]["prohibit"] == []
