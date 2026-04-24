from experimental.preprocessor.output_validation import (
    _is_allowed_directive,
    parse_precompiler_output,
    validate_precompiler_output,
)


def test_is_allowed_directive_accepts_canonical_shapes() -> None:
    assert _is_allowed_directive("clear state")
    assert _is_allowed_directive("set premise concise replies")
    assert _is_allowed_directive("change premise to formal tone")
    assert _is_allowed_directive("use podman instead of docker")


def test_validate_text_accepts_canonical_directive() -> None:
    result = validate_precompiler_output("prohibit peanuts")
    assert result == {
        "classification": "directive",
        "output": "prohibit peanuts",
    }


def test_validate_text_accepts_exact_no_directive_sentinel() -> None:
    result = validate_precompiler_output("<NO_DIRECTIVE>")
    assert result == {
        "classification": "no_directive",
        "output": None,
    }


def test_validate_text_rejects_malformed_or_mixed_output_as_unknown() -> None:
    assert validate_precompiler_output("<NO_DIRECTIPLE>") == {
        "classification": "unknown",
        "output": None,
    }
    assert validate_precompiler_output("set premise to concise replies") == {
        "classification": "unknown",
        "output": None,
    }
    assert validate_precompiler_output("prohibit peanuts and use almonds") == {
        "classification": "unknown",
        "output": None,
    }


def test_validate_structured_output_accepts_strict_contract_shape() -> None:
    assert validate_precompiler_output(
        {
            "classification": "directive",
            "output": "clear state",
        }
    ) == {
        "classification": "directive",
        "output": "clear state",
    }

    assert validate_precompiler_output(
        {
            "classification": "no_directive",
            "output": None,
        }
    ) == {
        "classification": "no_directive",
        "output": None,
    }

    assert validate_precompiler_output(
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
        assert validate_precompiler_output(raw) == {
            "classification": "unknown",
            "output": None,
        }


def test_validate_text_parses_and_validates_json_contract() -> None:
    raw = '{"classification":"directive","output":"use docker"}'
    assert validate_precompiler_output(raw) == {
        "classification": "directive",
        "output": "use docker",
    }


def test_parse_returns_validated_directive_only() -> None:
    assert parse_precompiler_output("prohibit peanuts") == "prohibit peanuts"
    assert parse_precompiler_output("<NO_DIRECTIVE>") is None
    assert parse_precompiler_output("set premise to concise replies") is None
