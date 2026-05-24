from experimental.preprocessor.output_validation import (
    _is_allowed_directive,
    parse_preprocessor_output,
    validate_preprocessor_output,
)


def test_is_allowed_directive_accepts_canonical_shapes() -> None:
    assert _is_allowed_directive("clear state")
    assert _is_allowed_directive("set premise concise replies")
    assert _is_allowed_directive("change premise to formal tone")
    assert _is_allowed_directive("use podman instead of docker")


def test_validate_text_accepts_canonical_directive() -> None:
    result = validate_preprocessor_output("prohibit peanuts")
    assert result == {
        "classification": "directive",
        "output": "prohibit peanuts",
    }


def test_validate_text_accepts_exact_no_directive_sentinel() -> None:
    result = validate_preprocessor_output("<NO_DIRECTIVE>")
    assert result == {
        "classification": "no_directive",
        "output": None,
    }


def test_validate_text_rejects_malformed_or_mixed_output_as_unknown() -> None:
    assert validate_preprocessor_output("<NO_DIRECTIPLE>") == {
        "classification": "unknown",
        "output": None,
    }
    assert validate_preprocessor_output("set premise to concise replies") == {
        "classification": "unknown",
        "output": None,
    }
    assert validate_preprocessor_output("prohibit peanuts and use almonds") == {
        "classification": "unknown",
        "output": None,
    }


def test_validate_structured_output_accepts_strict_contract_shape() -> None:
    assert validate_preprocessor_output(
        {
            "classification": "directive",
            "output": "clear state",
        }
    ) == {
        "classification": "directive",
        "output": "clear state",
    }

    assert validate_preprocessor_output(
        {
            "classification": "no_directive",
            "output": None,
        }
    ) == {
        "classification": "no_directive",
        "output": None,
    }

    assert validate_preprocessor_output(
        {
            "classification": "unknown",
            "output": None,
        }
    ) == {
        "classification": "unknown",
        "output": None,
    }


def test_validate_structured_output_rejects_malformed_shape_or_payload_as_unknown() -> None:
    cases = [
        None,
        123,
        {},
        {"classification": "directive"},
        {"output": "clear state"},
        {"classification": "directive", "output": None},
        {"classification": "directive", "output": ""},
        {"classification": "directive", "output": "set premise to concise replies"},
        {"classification": "no_directive", "output": "clear state"},
        {"classification": "unknown", "output": "clear state"},
        {"classification": "unsupported_action", "output": None},
        {"classification": "directive", "output": "clear state\nreset policies"},
        {"classification": "directive", "output": "clear state", "extra": True},
        {"action": "prohibit", "item": "peanuts"},
    ]
    for raw in cases:
        assert validate_preprocessor_output(raw) == {
            "classification": "unknown",
            "output": None,
        }


def test_validate_text_parses_and_validates_json_contract() -> None:
    raw = '{"classification":"directive","output":"use docker"}'
    assert validate_preprocessor_output(raw) == {
        "classification": "directive",
        "output": "use docker",
    }


def test_parse_returns_validated_directive_only() -> None:
    assert parse_preprocessor_output("prohibit peanuts") == "prohibit peanuts"
    assert parse_preprocessor_output("<NO_DIRECTIVE>") is None
    assert parse_preprocessor_output("set premise to concise replies") is None


def test_parse_with_source_input_rejects_premise_near_miss_canonicalization() -> None:
    assert (
        parse_preprocessor_output(
            "set premise concise replies",
            source_input="set premise to concise replies",
        )
        is None
    )
    assert (
        parse_preprocessor_output(
            "change premise to concise replies",
            source_input="change premise concise replies",
        )
        is None
    )


def test_validation_with_source_input_rejects_premise_near_miss_canonicalization() -> None:
    assert validate_preprocessor_output(
        "set premise concise replies",
        source_input="set premise to concise replies",
    ) == {
        "classification": "unknown",
        "output": None,
    }
    assert validate_preprocessor_output(
        "change premise to concise replies",
        source_input="change premise concise replies",
    ) == {
        "classification": "unknown",
        "output": None,
    }


def test_validation_with_source_input_allows_other_directives() -> None:
    assert validate_preprocessor_output(
        "prohibit peanuts",
        source_input="prohibit peanuts",
    ) == {
        "classification": "directive",
        "output": "prohibit peanuts",
    }
    assert validate_preprocessor_output(
        "use coconut milk",
        source_input="what is a simple curry recipe?",
    ) == {
        "classification": "unknown",
        "output": None,
    }


def test_validation_with_source_input_rejects_boundary_unsafe_fallback_rewrites() -> None:
    cases = [
        ("ok. prohibit peanuts", "prohibit peanuts"),
        ("clear premise\nreset policies", "clear premise"),
        ("```\nuse docker\n```", "use docker"),
        ("the command is `use docker`", "use docker"),
        ('the docs say "use docker"', "use docker"),
        ("use docker and explain why", "use docker"),
        ("can you use docker?", "use docker"),
    ]
    for source_input, fallback_output in cases:
        assert validate_preprocessor_output(
            fallback_output,
            source_input=source_input,
        ) == {
            "classification": "unknown",
            "output": None,
        }


def test_validation_with_source_input_preserves_safe_whole_message_canonicalization() -> None:
    cases = [
        ("Use Docker", "use docker"),
        ("  use    docker  ", "use docker"),
        ("clear state.", "clear state"),
        ("reset policies!", "reset policies"),
        ("(clear state)", "clear state"),
        ("[clear state]", "clear state"),
        ('use "docker"', 'use "docker"'),
    ]
    for source_input, fallback_output in cases:
        assert validate_preprocessor_output(
            fallback_output,
            source_input=source_input,
        ) == {
            "classification": "directive",
            "output": fallback_output,
        }


def test_validation_with_source_input_allows_strict_structured_contract_self_input() -> None:
    assert validate_preprocessor_output(
        '{"classification":"directive","output":"prohibit peanuts"}',
        source_input='{"classification":"directive","output":"prohibit peanuts"}',
    ) == {
        "classification": "directive",
        "output": "prohibit peanuts",
    }
