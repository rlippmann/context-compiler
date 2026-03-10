from context_compiler import create_engine
from context_compiler.engine import DecisionKind


def test_decision_kind_strenum_behavior() -> None:
    for kind in DecisionKind:
        assert kind == kind.value
        assert str(kind) == kind.value
        assert DecisionKind(kind.value) is kind


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
