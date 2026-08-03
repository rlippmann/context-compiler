from context_compiler import DECISION_NO_DIRECTIVE, DECISION_UPDATE, create_engine


def test_parser_trims_leading_space_for_canonical_directive() -> None:
    engine = create_engine()

    decision = engine.step(" set premise concise")

    assert decision == {
        "kind": DECISION_UPDATE,
        "state": {"premise": "concise", "policies": {}, "version": 2},
    }
    assert engine.state == {"premise": "concise", "policies": {}, "version": 2}


def test_parser_does_not_accept_conversational_aliases() -> None:
    engine = create_engine()

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
        assert decision["kind"] == DECISION_NO_DIRECTIVE

    assert engine.state == {"premise": None, "policies": {}, "version": 2}


def test_empty_policy_payloads_and_incomplete_replacement_remain_no_directive() -> None:
    engine = create_engine()
    before = engine.state

    for text in ["use", "use ", "use    "]:
        assert engine.step(text) == {"kind": DECISION_NO_DIRECTIVE}
        assert engine.state == before

    for text in ["prohibit", "prohibit ", "prohibit    "]:
        assert engine.step(text) == {"kind": DECISION_NO_DIRECTIVE}
        assert engine.state == before

    for text in [
        "use x instead of",
        "use x instead of ",
        "use  instead of y",
        "use   instead of y",
        "use instead of y",
    ]:
        assert engine.step(text) == {"kind": DECISION_NO_DIRECTIVE}
        assert engine.state == before

    assert engine.step("remove policy\tdocker")["kind"] == DECISION_UPDATE
    assert engine.state == before


def test_lexical_normalization_and_non_directive_near_misses() -> None:
    engine = create_engine()
    assert engine.step("clear premise ")["kind"] == DECISION_UPDATE
    assert engine.step("reset policies ")["kind"] == DECISION_UPDATE
    assert engine.step("clear state ")["kind"] == DECISION_UPDATE
    assert engine.step("remove policy\tdocker")["kind"] == DECISION_UPDATE
    assert engine.step("Use docker")["kind"] == DECISION_UPDATE
    assert engine.step("use\tdocker")["kind"] == DECISION_UPDATE
    assert engine.step("don't Use docker")["kind"] == DECISION_NO_DIRECTIVE
    assert engine.step("don't use")["kind"] == DECISION_NO_DIRECTIVE

    assert engine.state == {"premise": None, "policies": {"docker": "use"}, "version": 2}


def test_premise_to_variant_near_misses_remain_no_directive() -> None:
    engine = create_engine()
    before = engine.state

    set_variant = engine.step("set premise to concise")
    change_variant = engine.step("change premise concise")

    assert set_variant == {"kind": DECISION_NO_DIRECTIVE}
    assert change_variant == {"kind": DECISION_NO_DIRECTIVE}
    assert before == engine.state


def test_remove_policy_missing_or_whitespace_payload_remains_no_directive() -> None:
    engine = create_engine()
    before = engine.state

    first = engine.step("remove policy")
    second = engine.step("remove policy   ")

    assert first == {"kind": DECISION_NO_DIRECTIVE}
    assert second == {"kind": DECISION_NO_DIRECTIVE}
    assert engine.state == before


def test_invalid_replacement_does_not_block_following_directives() -> None:
    engine = create_engine()
    first = engine.step("use kubectl instead of docker")
    assert first["kind"] == DECISION_UPDATE

    second = engine.step("set premise concise")
    assert second == {
        "kind": DECISION_UPDATE,
        "state": {"premise": "concise", "policies": {"kubectl": "use"}, "version": 2},
    }
    assert engine.state == {
        "premise": "concise",
        "policies": {"kubectl": "use"},
        "version": 2,
    }


def test_replace_update_independent_followup_is_no_directive() -> None:
    engine = create_engine()
    first = engine.step("use kubectl instead of docker")
    second = engine.step("sounds good")

    assert first["kind"] == DECISION_UPDATE
    assert second == {"kind": DECISION_NO_DIRECTIVE}
