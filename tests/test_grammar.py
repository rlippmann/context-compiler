from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

import context_compiler.grammar as grammar_module
from context_compiler.grammar import (
    CanonicalDirective,
    DirectiveKind,
    DirectiveMetadata,
    DirectiveSyntaxFailure,
    InvalidDirectiveSyntax,
    decompose_directive,
    get_directive_metadata,
)


def test_directive_kind_members_and_values() -> None:
    assert [member.name for member in DirectiveKind] == [
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
    assert [member.value for member in DirectiveKind] == [
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
    assert DirectiveKind("set_premise") is DirectiveKind.SET_PREMISE


def test_directive_syntax_failure_members_and_values() -> None:
    assert [member.name for member in DirectiveSyntaxFailure] == [
        "COMPOUND_DIRECTIVE",
        "MISSING_REQUIRED_OPERAND",
        "MALFORMED_DIRECTIVE",
    ]
    assert [member.value for member in DirectiveSyntaxFailure] == [
        "compound_directive",
        "missing_required_operand",
        "malformed_directive",
    ]
    assert (
        DirectiveSyntaxFailure("missing_required_operand")
        is DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND
    )


def test_canonical_directive_is_frozen_and_slotted() -> None:
    directive = CanonicalDirective(
        kind=DirectiveKind.USE_ITEM,
        operands={"item": "docker"},
    )
    assert directive.__slots__ == ("kind", "operands")
    assert directive.text == "use docker"
    assert isinstance(directive.operands, MappingProxyType)
    with pytest.raises(FrozenInstanceError):
        directive.kind = DirectiveKind.PROHIBIT_ITEM  # type: ignore[misc]


def test_canonical_directive_copies_constructor_operands() -> None:
    operands = {"item": "docker"}
    directive = CanonicalDirective(kind=DirectiveKind.USE_ITEM, operands=operands)

    operands["item"] = "podman"

    assert dict(directive.operands) == {"item": "docker"}
    assert directive.text == "use docker"


def test_directive_metadata_is_frozen_and_slotted() -> None:
    metadata = DirectiveMetadata(
        kind=DirectiveKind.USE_ITEM,
        canonical_start="use",
        operand_names=("item",),
    )

    assert metadata.__slots__ == ("kind", "canonical_start", "operand_names")
    with pytest.raises(FrozenInstanceError):
        metadata.kind = DirectiveKind.PROHIBIT_ITEM  # type: ignore[misc]


@pytest.mark.parametrize(
    ("text", "expected_kind", "expected_operands"),
    [
        ("set premise concise replies", DirectiveKind.SET_PREMISE, {"value": "concise replies"}),
        (
            "set premise we must use gaap",
            DirectiveKind.SET_PREMISE,
            {"value": "we must use gaap"},
        ),
        (
            "set premise users may prohibit unsafe operations",
            DirectiveKind.SET_PREMISE,
            {"value": "users may prohibit unsafe operations"},
        ),
        (
            "set premise vegetarian and use docker",
            DirectiveKind.SET_PREMISE,
            {"value": "vegetarian and use docker"},
        ),
        (
            "set premise The system uses legacy tooling. Migration is planned.",
            DirectiveKind.SET_PREMISE,
            {"value": "The system uses legacy tooling. Migration is planned."},
        ),
        (
            "change premise to use docker for compatibility",
            DirectiveKind.CHANGE_PREMISE,
            {"value": "use docker for compatibility"},
        ),
        ("change premise to formal tone", DirectiveKind.CHANGE_PREMISE, {"value": "formal tone"}),
        ("use docker", DirectiveKind.USE_ITEM, {"item": "docker"}),
        ("prohibit peanuts", DirectiveKind.PROHIBIT_ITEM, {"item": "peanuts"}),
        ("remove policy docker", DirectiveKind.REMOVE_POLICY, {"item": "docker"}),
        (
            "use podman instead of docker",
            DirectiveKind.REPLACE_USE,
            {"new_item": "podman", "old_item": "docker"},
        ),
        ("clear premise", DirectiveKind.CLEAR_PREMISE, {}),
        ("reset policies", DirectiveKind.RESET_POLICIES, {}),
        ("clear state", DirectiveKind.CLEAR_STATE, {}),
    ],
)
def test_decompose_directive_accepts_each_canonical_family(
    text: str, expected_kind: DirectiveKind, expected_operands: dict[str, str]
) -> None:
    decomposed = decompose_directive(text)
    assert decomposed == CanonicalDirective(
        kind=expected_kind,
        operands=expected_operands,
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
            "set premise",
            InvalidDirectiveSyntax(
                failure=DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=DirectiveKind.SET_PREMISE,
                missing_operand="value",
            ),
        ),
        (
            "change premise to",
            InvalidDirectiveSyntax(
                failure=DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=DirectiveKind.CHANGE_PREMISE,
                missing_operand="value",
            ),
        ),
        (
            "use",
            InvalidDirectiveSyntax(
                failure=DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=DirectiveKind.USE_ITEM,
                missing_operand="item",
            ),
        ),
        (
            "prohibit",
            InvalidDirectiveSyntax(
                failure=DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=DirectiveKind.PROHIBIT_ITEM,
                missing_operand="item",
            ),
        ),
        (
            "remove policy",
            InvalidDirectiveSyntax(
                failure=DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=DirectiveKind.REMOVE_POLICY,
                missing_operand="item",
            ),
        ),
        (
            "use x instead of",
            InvalidDirectiveSyntax(
                failure=DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=DirectiveKind.REPLACE_USE,
                missing_operand="old_item",
            ),
        ),
        (
            "use instead of y",
            InvalidDirectiveSyntax(
                failure=DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=DirectiveKind.REPLACE_USE,
                missing_operand="new_item",
            ),
        ),
        (
            "set premise to concise",
            InvalidDirectiveSyntax(
                failure=DirectiveSyntaxFailure.MALFORMED_DIRECTIVE,
                directive_kind=DirectiveKind.SET_PREMISE,
            ),
        ),
        (
            "change premise concise",
            InvalidDirectiveSyntax(
                failure=DirectiveSyntaxFailure.MALFORMED_DIRECTIVE,
            ),
        ),
        (
            "use docker and prohibit peanuts",
            InvalidDirectiveSyntax(
                failure=DirectiveSyntaxFailure.COMPOUND_DIRECTIVE,
            ),
        ),
        (
            "use docker\nprohibit peanuts",
            InvalidDirectiveSyntax(
                failure=DirectiveSyntaxFailure.COMPOUND_DIRECTIVE,
            ),
        ),
        (
            "clear state then set premise project",
            InvalidDirectiveSyntax(
                failure=DirectiveSyntaxFailure.COMPOUND_DIRECTIVE,
            ),
        ),
        (
            "set premise project\nuse docker",
            InvalidDirectiveSyntax(
                failure=DirectiveSyntaxFailure.COMPOUND_DIRECTIVE,
            ),
        ),
        (
            "use\ninstead of docker",
            None,
        ),
    ],
)
def test_decompose_directive_marks_invalid_directive_syntax(
    text: str, expected: InvalidDirectiveSyntax | None
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
    ("inputs", "expected_text"),
    [
        (["use docker", "Use docker", " use\tdocker "], "use docker"),
        (
            [
                "change premise to formal tone",
                "Change premise to formal tone",
                " change\tpremise\tto\tformal tone ",
            ],
            "change premise to formal tone",
        ),
        (
            [
                "use podman instead of docker",
                "Use podman instead of docker",
                " use\tpodman\tinstead\tof\tdocker ",
            ],
            "use podman instead of docker",
        ),
    ],
)
def test_equivalent_accepted_inputs_share_canonical_text(
    inputs: list[str], expected_text: str
) -> None:
    for text in inputs:
        directive = decompose_directive(text)
        assert isinstance(directive, CanonicalDirective)
        assert directive.text == expected_text


@pytest.mark.parametrize(
    ("directive", "expected_text"),
    [
        (
            CanonicalDirective(
                kind=DirectiveKind.USE_ITEM,
                operands={"item": "docker"},
            ),
            "use docker",
        ),
        (
            CanonicalDirective(
                kind=DirectiveKind.CHANGE_PREMISE,
                operands={"value": "formal tone"},
            ),
            "change premise to formal tone",
        ),
        (
            CanonicalDirective(
                kind=DirectiveKind.REPLACE_USE,
                operands={"new_item": "podman", "old_item": "docker"},
            ),
            "use podman instead of docker",
        ),
    ],
)
def test_canonical_directive_text_is_derived_from_kind_and_operands(
    directive: CanonicalDirective, expected_text: str
) -> None:
    assert directive.text == expected_text


@pytest.mark.parametrize(
    ("kind", "operands", "expected"),
    [
        (DirectiveKind.SET_PREMISE, {"value": "concise replies"}, "set premise concise replies"),
        (
            DirectiveKind.CHANGE_PREMISE,
            {"value": "formal tone"},
            "change premise to formal tone",
        ),
        (DirectiveKind.USE_ITEM, {"item": "docker"}, "use docker"),
        (DirectiveKind.PROHIBIT_ITEM, {"item": "peanuts"}, "prohibit peanuts"),
        (DirectiveKind.REMOVE_POLICY, {"item": "docker"}, "remove policy docker"),
        (
            DirectiveKind.REPLACE_USE,
            {"new_item": "podman", "old_item": "docker"},
            "use podman instead of docker",
        ),
        (DirectiveKind.CLEAR_PREMISE, {}, "clear premise"),
        (DirectiveKind.RESET_POLICIES, {}, "reset policies"),
        (DirectiveKind.CLEAR_STATE, {}, "clear state"),
    ],
)
def test_render_directive_outputs_exact_canonical_syntax(
    kind: DirectiveKind, operands: dict[str, str], expected: str
) -> None:
    rendered = grammar_module._render_directive(kind, **operands)
    assert rendered == expected
    directive = decompose_directive(rendered)
    assert directive is not None
    assert directive.kind is kind


@pytest.mark.parametrize(
    ("kind", "operands", "message"),
    [
        (DirectiveKind.SET_PREMISE, {}, "Missing required operands"),
        (DirectiveKind.REPLACE_USE, {"new_item": "podman"}, "Missing required operands"),
        (
            DirectiveKind.CLEAR_STATE,
            {"item": "docker"},
            "Unexpected operands",
        ),
        (
            DirectiveKind.USE_ITEM,
            {"value": "docker"},
            "Missing required operands",
        ),
        (
            DirectiveKind.USE_ITEM,
            {"item": "docker", "old_item": "podman"},
            "Unexpected operands",
        ),
        (
            DirectiveKind.SET_PREMISE,
            {"value": ""},
            "cannot be empty",
        ),
        (
            DirectiveKind.SET_PREMISE,
            {"value": "   "},
            "cannot be empty",
        ),
        (
            DirectiveKind.USE_ITEM,
            {"item": "docker and prohibit peanuts"},
            "canonical use_item directive",
        ),
        (
            DirectiveKind.USE_ITEM,
            {"item": "docker instead of podman"},
            "canonical use_item directive",
        ),
        (
            DirectiveKind.USE_ITEM,
            {"item": "instead of docker"},
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
    kind: DirectiveKind | str, operands: dict[str, str], message: str
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
        specs[DirectiveKind.SET_PREMISE] = object()  # type: ignore[index]
    spec = specs[DirectiveKind.SET_PREMISE]
    with pytest.raises(FrozenInstanceError):
        spec.kind = DirectiveKind.CHANGE_PREMISE  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        spec.canonical_start = "different"  # type: ignore[misc]


def test_public_grammar_all_includes_semantic_surface() -> None:
    assert grammar_module.__all__ == [
        "DirectiveKind",
        "DirectiveSyntaxFailure",
        "DirectiveMetadata",
        "CanonicalDirective",
        "InvalidDirectiveSyntax",
        "get_directive_metadata",
        "decompose_directive",
    ]


def test_get_directive_metadata_returns_immutable_view_derived_from_specs() -> None:
    metadata = get_directive_metadata()

    assert metadata == tuple(
        DirectiveMetadata(
            kind=spec.kind,
            canonical_start=spec.canonical_start,
            operand_names=spec.operand_names,
        )
        for spec in grammar_module._DIRECTIVE_SPECS.values()
    )
    assert metadata[0] is grammar_module._PUBLIC_DIRECTIVE_METADATA[0]
    with pytest.raises(AttributeError):
        metadata.append(  # type: ignore[attr-defined]
            DirectiveMetadata(
                kind=DirectiveKind.CLEAR_STATE,
                canonical_start="clear state",
                operand_names=(),
            )
        )
    with pytest.raises(FrozenInstanceError):
        metadata[0].operand_names = ()  # type: ignore[misc]


def test_get_directive_metadata_reports_expected_public_fields() -> None:
    assert get_directive_metadata() == (
        DirectiveMetadata(
            kind=DirectiveKind.SET_PREMISE,
            canonical_start="set premise",
            operand_names=("value",),
        ),
        DirectiveMetadata(
            kind=DirectiveKind.CHANGE_PREMISE,
            canonical_start="change premise to",
            operand_names=("value",),
        ),
        DirectiveMetadata(
            kind=DirectiveKind.USE_ITEM,
            canonical_start="use",
            operand_names=("item",),
        ),
        DirectiveMetadata(
            kind=DirectiveKind.PROHIBIT_ITEM,
            canonical_start="prohibit",
            operand_names=("item",),
        ),
        DirectiveMetadata(
            kind=DirectiveKind.REMOVE_POLICY,
            canonical_start="remove policy",
            operand_names=("item",),
        ),
        DirectiveMetadata(
            kind=DirectiveKind.REPLACE_USE,
            canonical_start="use",
            operand_names=("new_item", "old_item"),
        ),
        DirectiveMetadata(
            kind=DirectiveKind.CLEAR_PREMISE,
            canonical_start="clear premise",
            operand_names=(),
        ),
        DirectiveMetadata(
            kind=DirectiveKind.RESET_POLICIES,
            canonical_start="reset policies",
            operand_names=(),
        ),
        DirectiveMetadata(
            kind=DirectiveKind.CLEAR_STATE,
            canonical_start="clear state",
            operand_names=(),
        ),
    )


def test_decompose_directive_rejects_near_miss_without_required_delimiter() -> None:
    assert decompose_directive("clear statex") is None
    assert decompose_directive("usex docker") is None


def test_render_directive_rejects_non_string_operands() -> None:
    with pytest.raises(ValueError, match="must be a string"):
        grammar_module._render_directive(DirectiveKind.SET_PREMISE, value=123)  # type: ignore[arg-type]


def test_serialize_canonical_directive_rejects_unsupported_kind() -> None:
    with pytest.raises(ValueError, match="Unsupported directive kind"):
        grammar_module._serialize_canonical_directive(
            "not_a_directive_kind",  # type: ignore[arg-type]
            MappingProxyType({}),
        )


@pytest.mark.parametrize(
    ("kind", "operands", "message"),
    [
        (DirectiveKind.SET_PREMISE, {}, "Missing required operands"),
        (DirectiveKind.REPLACE_USE, {"new_item": "podman"}, "Missing required operands"),
        (DirectiveKind.CLEAR_STATE, {"item": "docker"}, "Unexpected operands"),
        (DirectiveKind.USE_ITEM, {"value": "docker"}, "Missing required operands"),
        (DirectiveKind.USE_ITEM, {"item": "docker", "old_item": "podman"}, "Unexpected operands"),
        (DirectiveKind.SET_PREMISE, {"value": ""}, "cannot be empty"),
        (DirectiveKind.SET_PREMISE, {"value": "   "}, "cannot be empty"),
        (
            DirectiveKind.USE_ITEM,
            {"item": "docker and prohibit peanuts"},
            "canonical use_item directive",
        ),
        (
            DirectiveKind.USE_ITEM,
            {"item": "docker instead of podman"},
            "canonical use_item directive",
        ),
        (
            DirectiveKind.USE_ITEM,
            {"item": "instead of docker"},
            "canonical use_item directive",
        ),
        ("not_a_directive_kind", {"item": "docker"}, "Unsupported directive kind"),
    ],
)
def test_canonical_directive_rejects_invalid_construction(
    kind: DirectiveKind | str, operands: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        CanonicalDirective(kind=kind, operands=operands)  # type: ignore[arg-type]


def test_render_directive_builds_text_from_validated_canonical_directive() -> None:
    assert grammar_module._render_directive(DirectiveKind.USE_ITEM, item="docker") == "use docker"


def test_invalid_directive_syntax_is_frozen_and_slotted() -> None:
    invalid = InvalidDirectiveSyntax(
        failure=DirectiveSyntaxFailure.MALFORMED_DIRECTIVE,
        directive_kind=DirectiveKind.SET_PREMISE,
    )

    assert invalid.__slots__ == ("failure", "directive_kind", "missing_operand")
    with pytest.raises(FrozenInstanceError):
        invalid.failure = DirectiveSyntaxFailure.COMPOUND_DIRECTIVE  # type: ignore[misc]


def test_decompose_directive_returns_canonical_operands_for_use_item() -> None:
    parsed = decompose_directive("Use docker")

    assert parsed is not None
    assert parsed.text == "use docker"
    assert parsed.kind is DirectiveKind.USE_ITEM
    assert parsed.operands == {"item": "docker"}


def test_decompose_directive_returns_text_kind_and_operands_without_projection_layer() -> None:
    decomposed = decompose_directive(" use\tdocker ")

    assert decomposed is not None
    assert decomposed.text == "use docker"
    assert decomposed.kind is DirectiveKind.USE_ITEM
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


def test_internal_contains_multiple_premise_directives_ignores_non_directive_text() -> None:
    assert grammar_module._contains_multiple_premise_directives("hello there") is False


def test_parse_replace_use_rejects_blank_new_item() -> None:
    assert grammar_module._parse_replace_use("use \t instead of docker") is None


def test_parse_replace_use_rejects_embedded_delimiter_in_old_item() -> None:
    assert (
        grammar_module._parse_replace_use("use podman instead of docker instead of nerdctl") is None
    )


def test_decompose_directive_marks_use_with_embedded_replacement_delimiter_as_malformed() -> None:
    assert decompose_directive("use podman instead of docker instead of nerdctl") == (
        InvalidDirectiveSyntax(
            failure=DirectiveSyntaxFailure.MALFORMED_DIRECTIVE,
            directive_kind=DirectiveKind.USE_ITEM,
        )
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
        ("_USE_RE", "use docker", {"item": " \t "}),
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
