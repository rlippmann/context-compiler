from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

import context_compiler.grammar as grammar_module
from context_compiler.grammar import (
    DirectiveKind,
    ValidatedDirective,
    is_canonical_directive,
    render_directive,
    validate_directive,
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


def test_validated_directive_is_frozen_and_slotted() -> None:
    validated = ValidatedDirective(
        text="set premise concise replies",
        kind=DirectiveKind.SET_PREMISE,
    )
    assert validated.__slots__ == ("text", "kind")
    with pytest.raises(FrozenInstanceError):
        validated.text = "change premise to concise replies"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("text", "expected_kind"),
    [
        ("set premise concise replies", DirectiveKind.SET_PREMISE),
        ("change premise to formal tone", DirectiveKind.CHANGE_PREMISE),
        ("use docker", DirectiveKind.USE_ITEM),
        ("prohibit peanuts", DirectiveKind.PROHIBIT_ITEM),
        ("remove policy docker", DirectiveKind.REMOVE_POLICY),
        ("use podman instead of docker", DirectiveKind.REPLACE_USE),
        ("clear premise", DirectiveKind.CLEAR_PREMISE),
        ("reset policies", DirectiveKind.RESET_POLICIES),
        ("clear state", DirectiveKind.CLEAR_STATE),
    ],
)
def test_validate_directive_accepts_each_canonical_family(
    text: str, expected_kind: DirectiveKind
) -> None:
    validated = validate_directive(text)
    assert validated == ValidatedDirective(text=text, kind=expected_kind)
    assert is_canonical_directive(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hello there",
        "use",
        "prohibit",
        "remove policy",
        "use x instead of",
        "use instead of y",
        "set premise to concise",
        "change premise concise",
        "use docker and prohibit peanuts",
        "clear state then set premise project",
        "please use docker",
        '"use docker and prohibit peanuts"',
    ],
)
def test_validate_directive_rejects_non_canonical_inputs(text: str) -> None:
    assert validate_directive(text) is None
    assert is_canonical_directive(text) is False


@pytest.mark.parametrize(
    ("text", "expected_kind"),
    [
        (" set premise concise", DirectiveKind.SET_PREMISE),
        ("Use docker", DirectiveKind.USE_ITEM),
        ("use\tdocker", DirectiveKind.USE_ITEM),
    ],
)
def test_validate_directive_accepts_lexically_normalized_canonical_input(
    text: str, expected_kind: DirectiveKind
) -> None:
    validated = validate_directive(text)
    assert validated == ValidatedDirective(text=text, kind=expected_kind)


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
    rendered = render_directive(kind, **operands)
    assert rendered == expected
    validated = validate_directive(rendered)
    assert validated is not None
    assert validated.kind is kind


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
            DirectiveKind.SET_PREMISE,
            {"value": "use docker and prohibit peanuts"},
            "canonical set_premise directive",
        ),
        (
            DirectiveKind.USE_ITEM,
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
    kind: DirectiveKind | str, operands: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        render_directive(kind, **operands)


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


def test_internal_canonical_start_match_rejects_out_of_range_positions() -> None:
    assert grammar_module._match_canonical_directive_start("use docker", -1) is None
    assert grammar_module._match_canonical_directive_start("use docker", len("use docker")) is None


def test_validate_directive_rejects_near_miss_without_required_delimiter() -> None:
    assert validate_directive("clear statex") is None
    assert validate_directive("usex docker") is None


def test_render_directive_rejects_non_string_operands() -> None:
    with pytest.raises(ValueError, match="must be a string"):
        render_directive(DirectiveKind.SET_PREMISE, value=123)  # type: ignore[arg-type]


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
def test_validate_directive_defensively_rejects_when_branch_regex_match_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    pattern_name: str,
    text: str,
) -> None:
    monkeypatch.setattr(grammar_module, pattern_name, _FakePattern(None))

    assert validate_directive(text) is None


@pytest.mark.parametrize(
    ("pattern_name", "text", "groups"),
    [
        ("_CHANGE_PREMISE_RE", "change premise to concise", {"value": " \t "}),
        ("_PROHIBIT_RE", "prohibit docker", {"item": " \t "}),
        ("_REMOVE_POLICY_RE", "remove policy docker", {"item": " \t "}),
    ],
)
def test_validate_directive_defensively_rejects_whitespace_only_operands_after_match(
    monkeypatch: pytest.MonkeyPatch,
    pattern_name: str,
    text: str,
    groups: dict[str, str],
) -> None:
    monkeypatch.setattr(grammar_module, pattern_name, _FakePattern(_FakeMatch(groups)))

    assert validate_directive(text) is None
