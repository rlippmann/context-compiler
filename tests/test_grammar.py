from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

import context_compiler.grammar as grammar_module
from context_compiler.grammar import (
    CanonicalDirective,
    InvalidDirectiveSyntax,
    _DirectiveKind,
    _DirectiveSyntaxFailure,
    decompose_directive,
)


def test_directive_kind_members_and_values() -> None:
    assert [member.name for member in _DirectiveKind] == [
        "SET_PREMISE",
        "CHANGE_PREMISE",
        "USE_ITEM",
        "PROHIBIT_ITEM",
        "REMOVE_POLICY",
        "REPLACE_USE",
        "CLEAR_PREMISE",
        "RESET_POLICIES",
        "CLEAR_STATE",
    ]
    assert [member.value for member in _DirectiveKind] == [
        "set_premise",
        "change_premise",
        "use_item",
        "prohibit_item",
        "remove_policy",
        "replace_use",
        "clear_premise",
        "reset_policies",
        "clear_state",
    ]
    assert _DirectiveKind("set_premise") is _DirectiveKind.SET_PREMISE


def test_canonical_directive_is_frozen_and_slotted() -> None:
    directive = CanonicalDirective(
        text="use docker",
        kind=_DirectiveKind.USE_ITEM,
        operands=MappingProxyType({"item": "docker"}),
    )
    assert directive.__slots__ == ("text", "kind", "operands")
    with pytest.raises(FrozenInstanceError):
        directive.kind = _DirectiveKind.PROHIBIT_ITEM  # type: ignore[misc]


@pytest.mark.parametrize(
    ("text", "expected_kind", "expected_operands"),
    [
        ("set premise concise replies", _DirectiveKind.SET_PREMISE, {"value": "concise replies"}),
        ("change premise to formal tone", _DirectiveKind.CHANGE_PREMISE, {"value": "formal tone"}),
        ("use docker", _DirectiveKind.USE_ITEM, {"item": "docker"}),
        ("prohibit peanuts", _DirectiveKind.PROHIBIT_ITEM, {"item": "peanuts"}),
        ("remove policy docker", _DirectiveKind.REMOVE_POLICY, {"item": "docker"}),
        (
            "use podman instead of docker",
            _DirectiveKind.REPLACE_USE,
            {"new_item": "podman", "old_item": "docker"},
        ),
        ("clear premise", _DirectiveKind.CLEAR_PREMISE, {}),
        ("reset policies", _DirectiveKind.RESET_POLICIES, {}),
        ("clear state", _DirectiveKind.CLEAR_STATE, {}),
    ],
)
def test_decompose_directive_accepts_each_canonical_family(
    text: str, expected_kind: _DirectiveKind, expected_operands: dict[str, str]
) -> None:
    decomposed = decompose_directive(text)
    assert decomposed == CanonicalDirective(
        text=text,
        kind=expected_kind,
        operands=MappingProxyType(expected_operands),
    )


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hello there",
        "please use docker",
        '"use docker and prohibit peanuts"',
    ],
)
def test_decompose_directive_returns_none_when_no_directive_is_present(text: str) -> None:
    assert decompose_directive(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "use",
            InvalidDirectiveSyntax(
                failure=_DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=_DirectiveKind.USE_ITEM,
                missing_operand="item",
            ),
        ),
        (
            "prohibit",
            InvalidDirectiveSyntax(
                failure=_DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=_DirectiveKind.PROHIBIT_ITEM,
                missing_operand="item",
            ),
        ),
        (
            "remove policy",
            InvalidDirectiveSyntax(
                failure=_DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=_DirectiveKind.REMOVE_POLICY,
                missing_operand="item",
            ),
        ),
        (
            "use x instead of",
            InvalidDirectiveSyntax(
                failure=_DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=_DirectiveKind.REPLACE_USE,
                missing_operand="old_item",
            ),
        ),
        (
            "use instead of y",
            InvalidDirectiveSyntax(
                failure=_DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=_DirectiveKind.REPLACE_USE,
                missing_operand="new_item",
            ),
        ),
        (
            "set premise to concise",
            InvalidDirectiveSyntax(
                failure=_DirectiveSyntaxFailure.MALFORMED_DIRECTIVE,
                directive_kind=_DirectiveKind.SET_PREMISE,
            ),
        ),
        (
            "change premise concise",
            InvalidDirectiveSyntax(
                failure=_DirectiveSyntaxFailure.MALFORMED_DIRECTIVE,
            ),
        ),
        (
            "use docker and prohibit peanuts",
            InvalidDirectiveSyntax(
                failure=_DirectiveSyntaxFailure.COMPOUND_DIRECTIVE,
            ),
        ),
        (
            "clear state then set premise project",
            InvalidDirectiveSyntax(
                failure=_DirectiveSyntaxFailure.COMPOUND_DIRECTIVE,
            ),
        ),
    ],
)
def test_decompose_directive_marks_invalid_directive_syntax(
    text: str, expected: InvalidDirectiveSyntax
) -> None:
    assert decompose_directive(text) == expected


@pytest.mark.parametrize(
    ("text", "expected_operands"),
    [
        ("Use docker", {"item": "docker"}),
        ("use\tdocker", {"item": "docker"}),
        (" use docker ", {"item": "docker"}),
        ("Use    Docker", {"item": "Docker"}),
        ("use docker  engine", {"item": "docker  engine"}),
    ],
)
def test_decompose_directive_preserves_current_operand_casing_and_whitespace(
    text: str, expected_operands: dict[str, str]
) -> None:
    decomposed = decompose_directive(text)
    assert decomposed is not None
    assert dict(decomposed.operands) == expected_operands


@pytest.mark.parametrize(
    ("kind", "operands", "expected"),
    [
        (_DirectiveKind.SET_PREMISE, {"value": "concise replies"}, "set premise concise replies"),
        (
            _DirectiveKind.CHANGE_PREMISE,
            {"value": "formal tone"},
            "change premise to formal tone",
        ),
        (_DirectiveKind.USE_ITEM, {"item": "docker"}, "use docker"),
        (_DirectiveKind.PROHIBIT_ITEM, {"item": "peanuts"}, "prohibit peanuts"),
        (_DirectiveKind.REMOVE_POLICY, {"item": "docker"}, "remove policy docker"),
        (
            _DirectiveKind.REPLACE_USE,
            {"new_item": "podman", "old_item": "docker"},
            "use podman instead of docker",
        ),
        (_DirectiveKind.CLEAR_PREMISE, {}, "clear premise"),
        (_DirectiveKind.RESET_POLICIES, {}, "reset policies"),
        (_DirectiveKind.CLEAR_STATE, {}, "clear state"),
    ],
)
def test_render_directive_outputs_exact_canonical_syntax(
    kind: _DirectiveKind, operands: dict[str, str], expected: str
) -> None:
    rendered = grammar_module._render_directive(kind, **operands)
    assert rendered == expected
    directive = decompose_directive(rendered)
    assert directive is not None
    assert directive.kind is kind


@pytest.mark.parametrize(
    ("kind", "operands", "message"),
    [
        (_DirectiveKind.SET_PREMISE, {}, "Missing required operands"),
        (_DirectiveKind.REPLACE_USE, {"new_item": "podman"}, "Missing required operands"),
        (
            _DirectiveKind.CLEAR_STATE,
            {"item": "docker"},
            "Unexpected operands",
        ),
        (
            _DirectiveKind.USE_ITEM,
            {"value": "docker"},
            "Missing required operands",
        ),
        (
            _DirectiveKind.USE_ITEM,
            {"item": "docker", "old_item": "podman"},
            "Unexpected operands",
        ),
        (
            _DirectiveKind.SET_PREMISE,
            {"value": ""},
            "cannot be empty",
        ),
        (
            _DirectiveKind.SET_PREMISE,
            {"value": "   "},
            "cannot be empty",
        ),
        (
            _DirectiveKind.USE_ITEM,
            {"item": "docker and prohibit peanuts"},
            "canonical use_item directive",
        ),
        (
            _DirectiveKind.SET_PREMISE,
            {"value": "use docker and prohibit peanuts"},
            "canonical set_premise directive",
        ),
        (
            _DirectiveKind.USE_ITEM,
            {"item": "docker instead of podman"},
            "canonical use_item directive",
        ),
        (
            "not_a_directive_kind",  # type: ignore[arg-type]
            {"item": "docker"},
            "Unsupported directive kind",
        ),
    ],
)
def test_render_directive_rejects_invalid_operand_combinations(
    kind: _DirectiveKind | str, operands: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        grammar_module._render_directive(kind, **operands)


def test_no_exported_mutable_grammar_registry() -> None:
    assert "DIRECTIVE_SPECS" not in grammar_module.__all__
    assert "_DIRECTIVE_SPECS" not in grammar_module.__all__


def test_internal_grammar_specs_use_immutable_mapping() -> None:
    specs = grammar_module._DIRECTIVE_SPECS
    assert isinstance(specs, MappingProxyType)
    with pytest.raises(TypeError):
        specs[_DirectiveKind.SET_PREMISE] = object()  # type: ignore[index]
    spec = specs[_DirectiveKind.SET_PREMISE]
    with pytest.raises(FrozenInstanceError):
        spec.kind = _DirectiveKind.CHANGE_PREMISE  # type: ignore[misc]


def test_public_grammar_all_includes_semantic_surface() -> None:
    assert grammar_module.__all__ == [
        "CanonicalDirective",
        "InvalidDirectiveSyntax",
        "decompose_directive",
    ]


def test_decompose_directive_rejects_near_miss_without_required_delimiter() -> None:
    assert decompose_directive("clear statex") is None
    assert decompose_directive("usex docker") is None


def test_render_directive_rejects_non_string_operands() -> None:
    with pytest.raises(ValueError, match="must be a string"):
        grammar_module._render_directive(_DirectiveKind.SET_PREMISE, value=123)  # type: ignore[arg-type]


def test_render_directive_uses_decompose_directive_as_authoritative_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        grammar_module,
        "decompose_directive",
        lambda _: CanonicalDirective(
            text="use docker",
            kind=_DirectiveKind.USE_ITEM,
            operands=MappingProxyType({"item": "docker"}),
        ),
    )

    assert grammar_module._render_directive(_DirectiveKind.USE_ITEM, item="docker") == "use docker"


def test_render_directive_rejects_when_decompose_directive_disagrees_with_rendered_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        grammar_module,
        "decompose_directive",
        lambda _: CanonicalDirective(
            text="use docker",
            kind=_DirectiveKind.PROHIBIT_ITEM,
            operands=MappingProxyType({"item": "docker"}),
        ),
    )

    with pytest.raises(ValueError, match="canonical use_item directive"):
        grammar_module._render_directive(_DirectiveKind.USE_ITEM, item="docker")


def test_render_directive_rejects_when_decompose_directive_returns_noncanonical_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(grammar_module, "decompose_directive", lambda _: InvalidDirectiveSyntax())

    with pytest.raises(ValueError, match="canonical use_item directive"):
        grammar_module._render_directive(_DirectiveKind.USE_ITEM, item="docker")


def test_invalid_directive_syntax_is_frozen_and_slotted() -> None:
    invalid = InvalidDirectiveSyntax(
        failure=_DirectiveSyntaxFailure.MALFORMED_DIRECTIVE,
        directive_kind=_DirectiveKind.SET_PREMISE,
    )

    assert invalid.__slots__ == ("failure", "directive_kind", "missing_operand")
    with pytest.raises(FrozenInstanceError):
        invalid.failure = _DirectiveSyntaxFailure.COMPOUND_DIRECTIVE  # type: ignore[misc]


def test_decompose_directive_returns_canonical_operands_for_use_item() -> None:
    parsed = decompose_directive("use docker")

    assert parsed is not None
    assert parsed.text == "use docker"
    assert parsed.kind is _DirectiveKind.USE_ITEM
    assert parsed.operands == {"item": "docker"}


def test_decompose_directive_returns_text_kind_and_operands_without_projection_layer() -> None:
    decomposed = decompose_directive("use docker")

    assert decomposed is not None
    assert decomposed.text == "use docker"
    assert decomposed.kind is _DirectiveKind.USE_ITEM
    assert decomposed.operands == {"item": "docker"}


def test_internal_match_directive_token_rejects_truncated_and_non_whitespace_separator() -> None:
    assert (
        grammar_module._match_directive_token(
            "use",
            0,
            "use ",
            require_space_or_end=True,
        )
        is None
    )
    assert (
        grammar_module._match_directive_token(
            "set-premise concise",
            0,
            "set premise",
            require_space_or_end=True,
        )
        is None
    )


def test_internal_canonical_start_match_rejects_out_of_range_positions() -> None:
    assert grammar_module._match_canonical_directive_start("use docker", -1) is None
    assert grammar_module._match_canonical_directive_start("use docker", len("use docker")) is None


@pytest.mark.parametrize(
    ("text", "start", "expected"),
    [
        ("use docker", 0, len("use")),
        ("please use docker", 7, len("please use")),
        ("clear premise!", 0, len("clear premise")),
        ("abuse docker", 1, None),
    ],
)
def test_internal_match_canonical_directive_start_finds_public_prefix_shapes(
    text: str, start: int, expected: int | None
) -> None:
    assert grammar_module._match_canonical_directive_start(text, start) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("use docker and prohibit peanuts", True),
        ("hello there", False),
        ("use docker", False),
        ('"use docker and prohibit peanuts"', False),
    ],
)
def test_internal_contains_multiple_canonical_directives_reports_compound_detection(
    text: str, expected: bool
) -> None:
    assert grammar_module._contains_multiple_canonical_directives(text) is expected


def test_parse_replace_use_rejects_blank_new_item() -> None:
    assert grammar_module._parse_replace_use("use \t instead of docker") is None


def test_parse_replace_use_rejects_embedded_delimiter_in_old_item() -> None:
    assert (
        grammar_module._parse_replace_use("use podman instead of docker instead of nerdctl") is None
    )


def test_parse_replace_use_rejects_non_canonical_normalized_delimiter_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = grammar_module._normalized_for_matching

    def _patched(value: str) -> str:
        if value == "use podman instead of docker":
            return "use podman rather than docker"
        return original(value)

    monkeypatch.setattr(grammar_module, "_normalized_for_matching", _patched)

    assert grammar_module._parse_replace_use("use podman instead of docker") is None


class _FakeMatch:
    def __init__(self, groups: dict[str, str]) -> None:
        self._groups = groups

    def group(self, name: str) -> str:
        return self._groups[name]


class _FakePattern:
    def __init__(self, match: _FakeMatch | None) -> None:
        self._match = match

    def fullmatch(self, text: str) -> _FakeMatch | None:
        del text
        return self._match


@pytest.mark.parametrize(
    ("pattern_name", "text"),
    [
        ("_SET_PREMISE_RE", "set premise concise"),
        ("_CHANGE_PREMISE_RE", "change premise to concise"),
        ("_USE_RE", "use docker"),
        ("_PROHIBIT_RE", "prohibit docker"),
        ("_REMOVE_POLICY_RE", "remove policy docker"),
    ],
)
def test_decompose_directive_defensively_rejects_when_branch_regex_match_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    pattern_name: str,
    text: str,
) -> None:
    monkeypatch.setattr(grammar_module, pattern_name, _FakePattern(None))

    assert isinstance(decompose_directive(text), InvalidDirectiveSyntax)


@pytest.mark.parametrize(
    ("pattern_name", "text", "groups"),
    [
        ("_CHANGE_PREMISE_RE", "change premise to concise", {"value": " \t "}),
        ("_PROHIBIT_RE", "prohibit docker", {"item": " \t "}),
        ("_REMOVE_POLICY_RE", "remove policy docker", {"item": " \t "}),
    ],
)
def test_decompose_directive_defensively_rejects_whitespace_only_operands_after_match(
    monkeypatch: pytest.MonkeyPatch,
    pattern_name: str,
    text: str,
    groups: dict[str, str],
) -> None:
    monkeypatch.setattr(grammar_module, pattern_name, _FakePattern(_FakeMatch(groups)))

    assert isinstance(decompose_directive(text), InvalidDirectiveSyntax)
