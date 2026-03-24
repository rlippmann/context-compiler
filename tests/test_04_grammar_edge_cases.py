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


def test_empty_policy_payloads_and_incomplete_replacement_clarify() -> None:
    engine = create_engine()
    before = engine.state

    use_empty = "Policy item cannot be empty.\nUse 'use <item>' with a non-empty value."
    prohibit_empty = "Policy item cannot be empty.\nUse 'prohibit <item>' with a non-empty value."
    replacement_incomplete = (
        "Replacement requires both new and old items.\n"
        "Use 'use <new item> instead of <old item>' with non-empty values."
    )

    for text in ["use", "use ", "use    "]:
        assert engine.step(text) == {
            "kind": "clarify",
            "state": None,
            "prompt_to_user": use_empty,
        }
        assert engine.state == before

    for text in ["prohibit", "prohibit ", "prohibit    "]:
        assert engine.step(text) == {
            "kind": "clarify",
            "state": None,
            "prompt_to_user": prohibit_empty,
        }
        assert engine.state == before

    for text in [
        "use x instead of",
        "use x instead of ",
        "use  instead of y",
        "use   instead of y",
        "use instead of y",
    ]:
        assert engine.step(text) == {
            "kind": "clarify",
            "state": None,
            "prompt_to_user": replacement_incomplete,
        }
        assert engine.state == before

    assert engine.step("remove policy\tdocker")["kind"] == "passthrough"
    assert engine.state == before


def test_exact_match_near_misses_are_passthrough() -> None:
    engine = create_engine()
    inputs = [
        "clear premise ",
        "reset policies ",
        "clear state ",
        "remove policy\tdocker",
        "Use docker",
        "don't Use docker",
        "use\tdocker",
        "don't use",
    ]
    for text in inputs:
        assert engine.step(text)["kind"] == "passthrough"

    assert engine.state == {"premise": None, "policies": {}, "version": 2}


def test_remove_policy_missing_or_whitespace_payload_clarifies() -> None:
    engine = create_engine()
    before = engine.state

    first = engine.step("remove policy")
    second = engine.step("remove policy   ")

    expected = "Policy item cannot be empty.\nUse 'remove policy <item>' with a non-empty value."
    assert first == {"kind": "clarify", "state": None, "prompt_to_user": expected}
    assert second == {"kind": "clarify", "state": None, "prompt_to_user": expected}
    assert engine.state == before


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
