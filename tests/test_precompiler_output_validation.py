from experimental.preprocessor.constants import PRECOMPILER_NO_DIRECTIVE_SENTINEL
from experimental.preprocessor.output_validation import (
    _is_allowed_directive,
    _normalize_precompiler_output,
    parse_precompiler_output,
)


def test_normalize_accepts_exact_abstain_sentinel() -> None:
    assert _normalize_precompiler_output("<NO_DIRECTIVE>") == PRECOMPILER_NO_DIRECTIVE_SENTINEL


def test_normalize_repairs_known_malformed_abstain_tags() -> None:
    assert _normalize_precompiler_output("<NO_DIRECTIPLE>") == PRECOMPILER_NO_DIRECTIVE_SENTINEL
    assert _normalize_precompiler_output("<NO_DIRECTITIVE>") == PRECOMPILER_NO_DIRECTIVE_SENTINEL
    assert (
        _normalize_precompiler_output("<NO_DIRECT_DIRECTIVE>") == PRECOMPILER_NO_DIRECTIVE_SENTINEL
    )


def test_normalize_repairs_malformed_abstain_with_suffix_text() -> None:
    raw = "<NO_DIRECTDirective> Directive cannot be generated..."
    assert _normalize_precompiler_output(raw) == PRECOMPILER_NO_DIRECTIVE_SENTINEL


def test_normalize_preserves_last_non_empty_line_abstain_behavior() -> None:
    raw = "<NO_DIRECT Directive>\n<NO_DIRECTIVE>"
    assert _normalize_precompiler_output(raw) == PRECOMPILER_NO_DIRECTIVE_SENTINEL


def test_normalize_returns_none_for_non_string() -> None:
    assert _normalize_precompiler_output(None) is None
    assert _normalize_precompiler_output(123) is None


def test_is_allowed_directive_accepts_canonical_shapes() -> None:
    assert _is_allowed_directive("clear state")
    assert _is_allowed_directive("set premise concise replies")
    assert _is_allowed_directive("change premise to formal tone")
    assert _is_allowed_directive("use podman instead of docker")


def test_parse_accepts_valid_directive_and_rejects_malformed_directive() -> None:
    assert parse_precompiler_output("prohibit peanuts") == "prohibit peanuts"
    assert parse_precompiler_output("set premise to concise replies") is None
    assert parse_precompiler_output("wipe policies") is None


def test_parse_maps_malformed_abstain_to_canonical_sentinel() -> None:
    assert parse_precompiler_output("<NO_DIRECTIPLE>") == PRECOMPILER_NO_DIRECTIVE_SENTINEL
