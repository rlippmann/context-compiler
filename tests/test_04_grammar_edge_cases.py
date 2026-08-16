from _decision_test_helpers import assert_decision

from context_compiler import (
    DECISION_ERROR,
    DECISION_NO_DIRECTIVE,
    DECISION_UPDATE,
    Engine,
)


def _observations(engine: object) -> tuple[object, object]:
    return engine.premise, dict(engine.policies)


def test_step_trims_leading_space_for_canonical_directive() -> None:
    engine = Engine()

    decision = engine.step(" set premise concise")

    assert_decision(
        decision,
        {
            "kind": DECISION_UPDATE,
            "message": None,
        },
    )
    assert _observations(engine) == ("concise", {})


def test_step_does_not_accept_conversational_aliases() -> None:
    engine = Engine()

    for text in [
        "actually use docker",
        "I meant docker",
        "allow docker",
        "you can docker",
        "docker is fine",
        "please use docker",
        "I am using docker",
        "set docker",
    ]:
        decision = engine.step(text)
    assert decision.kind == DECISION_NO_DIRECTIVE

    assert _observations(engine) == (None, {})


def test_empty_policy_payloads_and_incomplete_replacement_remain_no_directive() -> None:
    engine = Engine()
    before = _observations(engine)

    for text in ["use", "use ", "use    "]:
        assert_decision(engine.step(text), {"kind": DECISION_NO_DIRECTIVE})
        assert _observations(engine) == before

    for text in ["prohibit", "prohibit ", "prohibit    "]:
        assert_decision(engine.step(text), {"kind": DECISION_NO_DIRECTIVE})
        assert _observations(engine) == before

    for text in [
        "use x instead of",
        "use x instead of ",
        "use  instead of y",
        "use   instead of y",
        "use instead of y",
    ]:
        assert_decision(engine.step(text), {"kind": DECISION_NO_DIRECTIVE})
        assert _observations(engine) == before

    assert engine.step("remove policy\tdocker").kind == DECISION_UPDATE
    assert _observations(engine) == before


def test_lexical_normalization_and_non_directive_near_misses() -> None:
    engine = Engine()
    assert engine.step("clear premise ").kind == DECISION_UPDATE
    assert engine.step("reset policies ").kind == DECISION_UPDATE
    assert engine.step("clear state ").kind == DECISION_UPDATE
    assert engine.step("remove policy\tdocker").kind == DECISION_UPDATE
    assert engine.step("Use docker").kind == DECISION_UPDATE
    assert engine.step("use\tdocker").kind == DECISION_UPDATE
    assert engine.step("don't Use docker").kind == DECISION_NO_DIRECTIVE
    assert engine.step("don't use").kind == DECISION_NO_DIRECTIVE

    assert _observations(engine) == (None, {"docker": "use"})


def test_premise_to_variant_near_misses_remain_no_directive() -> None:
    engine = Engine()
    before = _observations(engine)

    set_variant = engine.step("set premise to concise")
    change_variant = engine.step("change premise concise")

    assert_decision(set_variant, {"kind": DECISION_NO_DIRECTIVE})
    assert_decision(change_variant, {"kind": DECISION_NO_DIRECTIVE})
    assert before == _observations(engine)


def test_remove_policy_missing_or_whitespace_payload_remains_no_directive() -> None:
    engine = Engine()
    before = _observations(engine)

    first = engine.step("remove policy")
    second = engine.step("remove policy   ")

    assert_decision(first, {"kind": DECISION_NO_DIRECTIVE})
    assert_decision(second, {"kind": DECISION_NO_DIRECTIVE})
    assert _observations(engine) == before


def test_missing_source_replacement_error_does_not_block_following_directives() -> None:
    engine = Engine()
    first = engine.step("use kubectl instead of docker")
    assert first.kind == DECISION_ERROR

    second = engine.step("set premise concise")
    assert_decision(
        second,
        {
            "kind": DECISION_UPDATE,
            "message": None,
        },
    )
    assert _observations(engine) == ("concise", {})


def test_missing_source_replacement_error_independent_followup_is_no_directive() -> None:
    engine = Engine()
    first = engine.step("use kubectl instead of docker")
    second = engine.step("sounds good")

    assert first.kind == DECISION_ERROR
    assert_decision(second, {"kind": DECISION_NO_DIRECTIVE})
