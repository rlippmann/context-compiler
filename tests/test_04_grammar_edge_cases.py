from context_compiler import create_engine


def test_parser_requires_exact_prefix_without_leading_space() -> None:
    engine = create_engine()

    decision = engine.step(" set premise concise")

    assert decision["kind"] == "passthrough"
    assert engine.state == {"premise": None, "policies": {}, "version": 2}


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
        assert decision["kind"] == "passthrough"

    assert engine.state == {"premise": None, "policies": {}, "version": 2}


def test_replace_use_missing_side_is_passthrough() -> None:
    engine = create_engine()

    assert engine.step("use x instead of ")["kind"] == "passthrough"
    assert engine.step("use  instead of y")["kind"] == "passthrough"
    assert engine.step("use ")["kind"] == "passthrough"
    assert engine.step("prohibit ")["kind"] == "passthrough"
    assert engine.state == {"premise": None, "policies": {}, "version": 2}


def test_exact_match_near_misses_are_passthrough() -> None:
    engine = create_engine()
    inputs = [
        "clear premise ",
        "reset policies ",
        "clear state ",
        "Use docker",
        "don't Use docker",
        "use\tdocker",
        "don't use",
    ]
    for text in inputs:
        assert engine.step(text)["kind"] == "passthrough"

    assert engine.state == {"premise": None, "policies": {}, "version": 2}


def test_pending_blocks_directive_parsing_until_confirmation() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")

    first = engine.step("use kubectl instead of docker")
    assert first["kind"] == "clarify"

    # Would normally update, but pending must block parser.
    second = engine.step("set premise concise")
    assert second == first
    assert engine.state == {
        "premise": None,
        "policies": {"docker": "use", "kubectl": "prohibit"},
        "version": 2,
    }


def test_pending_rejects_non_confirmation_and_keeps_prompt() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")

    first = engine.step("use kubectl instead of docker")
    second = engine.step("sounds good")

    assert second == first
    expected = (
        '"kubectl" is currently prohibited. Did you mean to remove "docker" '
        'and use "kubectl" instead?'
    )
    assert second["prompt_to_user"] == expected
