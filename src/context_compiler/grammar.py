"""Immutable canonical grammar helpers for Context Compiler directives."""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class DirectiveKind(StrEnum):
    """Enumerate the supported canonical directive families."""

    SET_PREMISE = "set_premise"
    CHANGE_PREMISE = "change_premise"
    USE_ITEM = "use_item"
    PROHIBIT_ITEM = "prohibit_item"
    REMOVE_POLICY = "remove_policy"
    REPLACE_USE = "replace_use"
    CLEAR_PREMISE = "clear_premise"
    RESET_POLICIES = "reset_policies"
    CLEAR_STATE = "clear_state"


class DirectiveSyntaxFailure(StrEnum):
    """Enumerate minimal grammar failure categories for directive-shaped input."""

    COMPOUND_DIRECTIVE = "compound_directive"
    MISSING_REQUIRED_OPERAND = "missing_required_operand"
    MALFORMED_DIRECTIVE = "malformed_directive"


@dataclass(frozen=True, slots=True)
class CanonicalDirective:
    """Represent one parsed canonical directive and its named operands.

    ``text`` is the canonical serialized directive text derived from ``kind``
    and ``operands``.
    """

    kind: DirectiveKind
    operands: MappingProxyType[str, str]

    def __post_init__(self) -> None:
        normalized_kind = _normalize_directive_kind(self.kind)
        normalized_operands = _normalize_canonical_operands(normalized_kind, self.operands)
        object.__setattr__(self, "kind", normalized_kind)
        object.__setattr__(self, "operands", MappingProxyType(normalized_operands))

    @property
    def text(self) -> str:
        """Return the canonical serialized directive text."""
        return _serialize_canonical_directive(self.kind, self.operands)


@dataclass(frozen=True, slots=True)
class InvalidDirectiveSyntax:
    """Represent directive-shaped input that fails canonical syntax parsing."""

    failure: DirectiveSyntaxFailure = DirectiveSyntaxFailure.MALFORMED_DIRECTIVE
    directive_kind: DirectiveKind | None = None
    missing_operand: str | None = None


@dataclass(frozen=True, slots=True)
class _DirectiveSpec:
    kind: DirectiveKind
    canonical_start: str
    operand_names: tuple[str, ...]
    exact_text: str | None
    renderer: Callable[[MappingProxyType[str, str]], str]


@dataclass(frozen=True, slots=True)
class DirectiveMetadata:
    """Describe one canonical directive family without exposing parser internals."""

    kind: DirectiveKind
    canonical_start: str
    operand_names: tuple[str, ...]


_SET_PREMISE_START = "set premise"
_CHANGE_PREMISE_START = "change premise to"
_USE_START = "use"
_PROHIBIT_START = "prohibit"
_REMOVE_POLICY_START = "remove policy"
_SET_PREMISE_PREFIX = f"{_SET_PREMISE_START} "
_CHANGE_PREMISE_PREFIX = f"{_CHANGE_PREMISE_START} "
_USE_PREFIX = f"{_USE_START} "
_PROHIBIT_PREFIX = f"{_PROHIBIT_START} "
_REMOVE_POLICY_PREFIX = f"{_REMOVE_POLICY_START} "
_CLEAR_PREMISE_TEXT = "clear premise"
_RESET_POLICIES_TEXT = "reset policies"
_CLEAR_STATE_TEXT = "clear state"
_CHANGE_PREMISE_FAMILY = "change premise"
_INSTEAD_OF_DELIMITER = " instead of "
_ASCII_WHITESPACE = " \t\n\r\x0b\x0c"
_HORIZONTAL_WHITESPACE = " \t"
_KEYWORD_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
_SET_PREMISE_RE = re.compile(r"(?i)^set[ \t]+premise[ \t]+(?P<value>.+)$")
_CHANGE_PREMISE_RE = re.compile(r"(?i)^change[ \t]+premise[ \t]+to[ \t]+(?P<value>.+)$")
_USE_RE = re.compile(r"(?i)^use[ \t]+(?P<item>.+)$")
_PROHIBIT_RE = re.compile(r"(?i)^prohibit[ \t]+(?P<item>.+)$")
_REMOVE_POLICY_RE = re.compile(r"(?i)^remove[ \t]+policy[ \t]+(?P<item>.+)$")
_REPLACE_RE = re.compile(
    r"(?i)^use[ \t]+(?P<new_item>.*?)[ \t]+instead[ \t]+of[ \t]+(?P<old_item>.+)$"
)


def _render_with_prefix(
    prefix: str, operand_name: str
) -> Callable[[MappingProxyType[str, str]], str]:
    def _renderer(operands: MappingProxyType[str, str]) -> str:
        return f"{prefix}{operands[operand_name]}"

    return _renderer


def _render_replace_use(operands: MappingProxyType[str, str]) -> str:
    return f"{_USE_PREFIX}{operands['new_item']}{_INSTEAD_OF_DELIMITER}{operands['old_item']}"


def _render_exact(text: str) -> Callable[[MappingProxyType[str, str]], str]:
    def _renderer(operands: MappingProxyType[str, str]) -> str:
        assert not operands
        return text

    return _renderer


_DIRECTIVE_SPECS = MappingProxyType(
    {
        DirectiveKind.SET_PREMISE: _DirectiveSpec(
            kind=DirectiveKind.SET_PREMISE,
            canonical_start=_SET_PREMISE_START,
            operand_names=("value",),
            exact_text=None,
            renderer=_render_with_prefix(_SET_PREMISE_PREFIX, "value"),
        ),
        DirectiveKind.CHANGE_PREMISE: _DirectiveSpec(
            kind=DirectiveKind.CHANGE_PREMISE,
            canonical_start=_CHANGE_PREMISE_START,
            operand_names=("value",),
            exact_text=None,
            renderer=_render_with_prefix(_CHANGE_PREMISE_PREFIX, "value"),
        ),
        DirectiveKind.USE_ITEM: _DirectiveSpec(
            kind=DirectiveKind.USE_ITEM,
            canonical_start=_USE_START,
            operand_names=("item",),
            exact_text=None,
            renderer=_render_with_prefix(_USE_PREFIX, "item"),
        ),
        DirectiveKind.PROHIBIT_ITEM: _DirectiveSpec(
            kind=DirectiveKind.PROHIBIT_ITEM,
            canonical_start=_PROHIBIT_START,
            operand_names=("item",),
            exact_text=None,
            renderer=_render_with_prefix(_PROHIBIT_PREFIX, "item"),
        ),
        DirectiveKind.REMOVE_POLICY: _DirectiveSpec(
            kind=DirectiveKind.REMOVE_POLICY,
            canonical_start=_REMOVE_POLICY_START,
            operand_names=("item",),
            exact_text=None,
            renderer=_render_with_prefix(_REMOVE_POLICY_PREFIX, "item"),
        ),
        DirectiveKind.REPLACE_USE: _DirectiveSpec(
            kind=DirectiveKind.REPLACE_USE,
            canonical_start=_USE_START,
            operand_names=("new_item", "old_item"),
            exact_text=None,
            renderer=_render_replace_use,
        ),
        DirectiveKind.CLEAR_PREMISE: _DirectiveSpec(
            kind=DirectiveKind.CLEAR_PREMISE,
            canonical_start=_CLEAR_PREMISE_TEXT,
            operand_names=(),
            exact_text=_CLEAR_PREMISE_TEXT,
            renderer=_render_exact(_CLEAR_PREMISE_TEXT),
        ),
        DirectiveKind.RESET_POLICIES: _DirectiveSpec(
            kind=DirectiveKind.RESET_POLICIES,
            canonical_start=_RESET_POLICIES_TEXT,
            operand_names=(),
            exact_text=_RESET_POLICIES_TEXT,
            renderer=_render_exact(_RESET_POLICIES_TEXT),
        ),
        DirectiveKind.CLEAR_STATE: _DirectiveSpec(
            kind=DirectiveKind.CLEAR_STATE,
            canonical_start=_CLEAR_STATE_TEXT,
            operand_names=(),
            exact_text=_CLEAR_STATE_TEXT,
            renderer=_render_exact(_CLEAR_STATE_TEXT),
        ),
    }
)


def _starts_with_descriptor(spec: _DirectiveSpec) -> tuple[str, bool]:
    return (spec.canonical_start, bool(spec.operand_names))


def _unique_start_descriptors(specs: tuple[_DirectiveSpec, ...]) -> tuple[tuple[str, bool], ...]:
    descriptors: list[tuple[str, bool]] = []
    seen: set[tuple[str, bool]] = set()
    for spec in specs:
        descriptor = _starts_with_descriptor(spec)
        if descriptor not in seen:
            seen.add(descriptor)
            descriptors.append(descriptor)
    return tuple(descriptors)


_CANONICAL_START_ORDER = (
    DirectiveKind.CHANGE_PREMISE,
    DirectiveKind.SET_PREMISE,
    DirectiveKind.REMOVE_POLICY,
    DirectiveKind.RESET_POLICIES,
    DirectiveKind.CLEAR_PREMISE,
    DirectiveKind.CLEAR_STATE,
    DirectiveKind.PROHIBIT_ITEM,
    DirectiveKind.USE_ITEM,
)

_CANONICAL_DIRECTIVE_STARTS = _unique_start_descriptors(
    tuple(_DIRECTIVE_SPECS[kind] for kind in _CANONICAL_START_ORDER)
)

_DIRECTIVE_FAMILY_STARTS = (
    (_CHANGE_PREMISE_FAMILY, True),
    *_unique_start_descriptors(
        tuple(
            _DIRECTIVE_SPECS[kind]
            for kind in (
                DirectiveKind.SET_PREMISE,
                DirectiveKind.REMOVE_POLICY,
                DirectiveKind.RESET_POLICIES,
                DirectiveKind.CLEAR_PREMISE,
                DirectiveKind.CLEAR_STATE,
                DirectiveKind.PROHIBIT_ITEM,
                DirectiveKind.USE_ITEM,
            )
        )
    ),
)

_PUBLIC_DIRECTIVE_METADATA = tuple(
    DirectiveMetadata(
        kind=spec.kind,
        canonical_start=spec.canonical_start,
        operand_names=spec.operand_names,
    )
    for spec in _DIRECTIVE_SPECS.values()
)


def _trim_ascii_whitespace(text: str) -> str:
    return text.strip(_ASCII_WHITESPACE)


def _collapse_horizontal_whitespace(text: str) -> str:
    parts = text.replace("\t", " ").split(" ")
    return " ".join(part for part in parts if part != "")


def _normalized_for_matching(text: str) -> str:
    return _collapse_horizontal_whitespace(_trim_ascii_whitespace(text)).casefold()


def _operand_has_content(value: str) -> bool:
    return _trim_ascii_whitespace(value) != ""


def _operand_starts_with_token(value: str, token: str) -> bool:
    normalized = _normalized_for_matching(value)
    return normalized == token or normalized.startswith(f"{token} ")


def _match_canonical_directive_start(text: str, start: int) -> int | None:
    """Locate a canonical directive prefix at a given character position."""
    if start < 0 or start >= len(text):
        return None

    if start > 0 and text[start - 1] in _KEYWORD_CHARS:
        return None

    for token, require_space_or_end in _CANONICAL_DIRECTIVE_STARTS:
        end = _match_directive_token(text, start, token, require_space_or_end=require_space_or_end)
        if end is not None:
            return end

    return None


def _match_directive_token(
    text: str,
    start: int,
    token: str,
    *,
    require_space_or_end: bool,
) -> int | None:
    index = start
    token_index = 0

    while token_index < len(token):
        if index >= len(text):
            return None

        token_char = token[token_index]
        if token_char == " ":
            if text[index] not in _HORIZONTAL_WHITESPACE:
                return None
            while index < len(text) and text[index] in _HORIZONTAL_WHITESPACE:
                index += 1
            token_index += 1
            continue

        character = text[index]
        if "A" <= character <= "Z":
            character = chr(ord(character) + (ord("a") - ord("A")))
        if character != token_char:
            return None
        index += 1
        token_index += 1

    if index == len(text):
        return index

    next_char = text[index]
    if require_space_or_end:
        if next_char in _HORIZONTAL_WHITESPACE:
            return index
        return None

    if next_char in _KEYWORD_CHARS:
        return None
    return index


def _contains_multiple_canonical_directives(text: str) -> bool:
    """Report whether text contains more than one canonical directive start."""
    first_start = _match_canonical_directive_start(text, 0)
    if first_start is None:
        return False

    for index in range(first_start, len(text)):
        next_start = _match_canonical_directive_start(text, index)
        if next_start is not None:
            return True

    return False


def _contains_multiple_premise_directives(text: str) -> bool:
    """Report premise compounds without inspecting opaque premise payload text."""
    first_start = _match_canonical_directive_start(text, 0)
    if first_start is None:
        return False

    for index, character in enumerate(text[first_start:], start=first_start):
        if character == "\n" and _match_canonical_directive_start(text, index + 1) is not None:
            return True
    return False


def _starts_with_directive_family(text: str) -> bool:
    for token, require_space_or_end in _DIRECTIVE_FAMILY_STARTS:
        if (
            _match_directive_token(text, 0, token, require_space_or_end=require_space_or_end)
            is not None
        ):
            return True
    return False


def _parse_replace_use(trimmed_text: str) -> CanonicalDirective | None:
    match = _REPLACE_RE.fullmatch(trimmed_text)
    if match is None:
        return None
    new_item = match.group("new_item")
    old_item = match.group("old_item")
    if not _operand_has_content(new_item) or not _operand_has_content(old_item):
        return None
    if _INSTEAD_OF_DELIMITER in _normalized_for_matching(
        new_item
    ) or _INSTEAD_OF_DELIMITER in _normalized_for_matching(old_item):
        return None
    normalized_payload = _normalized_for_matching(trimmed_text)
    if normalized_payload.count(_INSTEAD_OF_DELIMITER) != 1:
        return None
    return CanonicalDirective(
        kind=DirectiveKind.REPLACE_USE,
        operands=MappingProxyType({"new_item": new_item, "old_item": old_item}),
    )


def _invalid_directive_syntax(
    failure: DirectiveSyntaxFailure,
    *,
    directive_kind: DirectiveKind | None = None,
    missing_operand: str | None = None,
) -> InvalidDirectiveSyntax:
    return InvalidDirectiveSyntax(
        failure=failure,
        directive_kind=directive_kind,
        missing_operand=missing_operand,
    )


def _normalize_directive_kind(kind: DirectiveKind | str) -> DirectiveKind:
    try:
        return kind if isinstance(kind, DirectiveKind) else DirectiveKind(kind)
    except ValueError as exc:
        raise ValueError(f"Unsupported directive kind: {kind!r}") from exc


def _normalize_canonical_operands(
    kind: DirectiveKind,
    operands: Mapping[str, str],
) -> dict[str, str]:
    spec = _DIRECTIVE_SPECS[kind]
    expected_names = set(spec.operand_names)
    actual_names = set(operands)
    unexpected_names = actual_names - expected_names
    missing_names = expected_names - actual_names
    if missing_names:
        missing = ", ".join(sorted(missing_names))
        raise ValueError(f"Missing required operands for {kind.value}: {missing}")
    if unexpected_names:
        unexpected = ", ".join(sorted(unexpected_names))
        raise ValueError(f"Unexpected operands for {kind.value}: {unexpected}")

    normalized_operands: dict[str, str] = {}
    for name in spec.operand_names:
        raw_value = operands[name]
        if not isinstance(raw_value, str):
            raise ValueError(f"Operand {name!r} for {kind.value} must be a string.")
        if not _operand_has_content(raw_value):
            raise ValueError(f"Operand {name!r} for {kind.value} cannot be empty.")
        normalized_operands[name] = raw_value

    _validate_operand_constraints(kind, normalized_operands)
    _validate_rendered_canonical_shape(kind, normalized_operands)
    return normalized_operands


def _validate_operand_constraints(kind: DirectiveKind, operands: Mapping[str, str]) -> None:
    if kind is DirectiveKind.SET_PREMISE:
        value = operands["value"]
        if _operand_starts_with_token(value, "to"):
            raise ValueError(f"Operands do not produce a canonical {kind.value} directive.")
        return

    if kind is DirectiveKind.USE_ITEM:
        item = operands["item"]
        normalized_item = _normalized_for_matching(item)
        if normalized_item == "instead of" or normalized_item.startswith("instead of "):
            raise ValueError(f"Operands do not produce a canonical {kind.value} directive.")
        if _INSTEAD_OF_DELIMITER in normalized_item:
            raise ValueError(f"Operands do not produce a canonical {kind.value} directive.")
        return

    if kind is DirectiveKind.REPLACE_USE:
        new_item = operands["new_item"]
        old_item = operands["old_item"]
        if _INSTEAD_OF_DELIMITER in _normalized_for_matching(
            new_item
        ) or _INSTEAD_OF_DELIMITER in _normalized_for_matching(old_item):
            raise ValueError(f"Operands do not produce a canonical {kind.value} directive.")


def _validate_rendered_canonical_shape(kind: DirectiveKind, operands: Mapping[str, str]) -> None:
    rendered = _serialize_canonical_directive(kind, MappingProxyType(dict(operands)))
    contains_compound = (
        _contains_multiple_premise_directives(rendered)
        if kind in {DirectiveKind.SET_PREMISE, DirectiveKind.CHANGE_PREMISE}
        else _contains_multiple_canonical_directives(rendered)
    )
    if contains_compound:
        raise ValueError(f"Operands do not produce a canonical {kind.value} directive.")


def decompose_directive(text: str) -> CanonicalDirective | InvalidDirectiveSyntax | None:
    """Parse one canonical directive into its semantic kind and operands.

    This determines whether ``text`` is a single canonical directive and, when
    it is, returns the directive kind plus canonical operand names with the
    original operand text preserved. It returns ``None`` when no canonical
    directive is present and returns ``InvalidDirectiveSyntax`` when the text is
    directive-shaped but not valid canonical syntax. It does not repair input,
    infer intent, or evaluate directive effects against compiler state.
    """
    trimmed_text = _trim_ascii_whitespace(text)
    if trimmed_text == "":
        return None
    if not _starts_with_directive_family(trimmed_text):
        return None
    premise_directive = _match_directive_token(
        trimmed_text, 0, _SET_PREMISE_START, require_space_or_end=True
    ) or _match_directive_token(trimmed_text, 0, _CHANGE_PREMISE_START, require_space_or_end=True)
    contains_compound = (
        _contains_multiple_premise_directives(trimmed_text)
        if premise_directive is not None
        else _contains_multiple_canonical_directives(trimmed_text)
    )
    if contains_compound:
        return _invalid_directive_syntax(DirectiveSyntaxFailure.COMPOUND_DIRECTIVE)

    normalized = _normalized_for_matching(trimmed_text)

    if normalized == _CLEAR_PREMISE_TEXT:
        return CanonicalDirective(kind=DirectiveKind.CLEAR_PREMISE, operands=MappingProxyType({}))
    if normalized == _RESET_POLICIES_TEXT:
        return CanonicalDirective(
            kind=DirectiveKind.RESET_POLICIES,
            operands=MappingProxyType({}),
        )
    if normalized == _CLEAR_STATE_TEXT:
        return CanonicalDirective(kind=DirectiveKind.CLEAR_STATE, operands=MappingProxyType({}))

    if normalized == "set premise":
        return _invalid_directive_syntax(
            DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
            directive_kind=DirectiveKind.SET_PREMISE,
            missing_operand="value",
        )

    if normalized.startswith("set premise "):
        match = _SET_PREMISE_RE.fullmatch(trimmed_text)
        if match is None:
            return _invalid_directive_syntax(
                DirectiveSyntaxFailure.MALFORMED_DIRECTIVE,
                directive_kind=DirectiveKind.SET_PREMISE,
            )
        value = match.group("value")
        if not _operand_has_content(value) or _operand_starts_with_token(value, "to"):
            return _invalid_directive_syntax(
                DirectiveSyntaxFailure.MALFORMED_DIRECTIVE,
                directive_kind=DirectiveKind.SET_PREMISE,
            )
        return CanonicalDirective(
            kind=DirectiveKind.SET_PREMISE,
            operands=MappingProxyType({"value": value}),
        )

    if normalized == "change premise to":
        return _invalid_directive_syntax(
            DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
            directive_kind=DirectiveKind.CHANGE_PREMISE,
            missing_operand="value",
        )

    if normalized.startswith("change premise to "):
        match = _CHANGE_PREMISE_RE.fullmatch(trimmed_text)
        if match is None:
            return _invalid_directive_syntax(
                DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=DirectiveKind.CHANGE_PREMISE,
                missing_operand="value",
            )
        value = match.group("value")
        if not _operand_has_content(value):
            return _invalid_directive_syntax(
                DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=DirectiveKind.CHANGE_PREMISE,
                missing_operand="value",
            )
        return CanonicalDirective(
            kind=DirectiveKind.CHANGE_PREMISE,
            operands=MappingProxyType({"value": value}),
        )

    replacement = _parse_replace_use(trimmed_text)
    if replacement is not None:
        return replacement

    if normalized == "use":
        return _invalid_directive_syntax(
            DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
            directive_kind=DirectiveKind.USE_ITEM,
            missing_operand="item",
        )

    if normalized.startswith("use "):
        match = _USE_RE.fullmatch(trimmed_text)
        if match is None:
            return _invalid_directive_syntax(
                DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=DirectiveKind.USE_ITEM,
                missing_operand="item",
            )
        item = match.group("item")
        normalized_item = _normalized_for_matching(item)
        if not _operand_has_content(item):
            return _invalid_directive_syntax(
                DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=DirectiveKind.USE_ITEM,
                missing_operand="item",
            )
        if normalized_item == "instead of" or normalized_item.startswith("instead of "):
            return _invalid_directive_syntax(
                DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=DirectiveKind.REPLACE_USE,
                missing_operand="new_item",
            )
        if normalized_item.endswith(" instead of"):
            return _invalid_directive_syntax(
                DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=DirectiveKind.REPLACE_USE,
                missing_operand="old_item",
            )
        if _INSTEAD_OF_DELIMITER in normalized_item:
            return _invalid_directive_syntax(
                DirectiveSyntaxFailure.MALFORMED_DIRECTIVE,
                directive_kind=DirectiveKind.USE_ITEM,
            )
        return CanonicalDirective(
            kind=DirectiveKind.USE_ITEM,
            operands=MappingProxyType({"item": item}),
        )

    if normalized == "prohibit":
        return _invalid_directive_syntax(
            DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
            directive_kind=DirectiveKind.PROHIBIT_ITEM,
            missing_operand="item",
        )

    if normalized.startswith("prohibit "):
        match = _PROHIBIT_RE.fullmatch(trimmed_text)
        if match is None:
            return _invalid_directive_syntax(
                DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=DirectiveKind.PROHIBIT_ITEM,
                missing_operand="item",
            )
        item = match.group("item")
        if not _operand_has_content(item):
            return _invalid_directive_syntax(
                DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=DirectiveKind.PROHIBIT_ITEM,
                missing_operand="item",
            )
        return CanonicalDirective(
            kind=DirectiveKind.PROHIBIT_ITEM,
            operands=MappingProxyType({"item": item}),
        )

    if normalized == "remove policy":
        return _invalid_directive_syntax(
            DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
            directive_kind=DirectiveKind.REMOVE_POLICY,
            missing_operand="item",
        )

    if normalized.startswith("remove policy "):
        match = _REMOVE_POLICY_RE.fullmatch(trimmed_text)
        if match is None:
            return _invalid_directive_syntax(
                DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=DirectiveKind.REMOVE_POLICY,
                missing_operand="item",
            )
        item = match.group("item")
        if not _operand_has_content(item):
            return _invalid_directive_syntax(
                DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND,
                directive_kind=DirectiveKind.REMOVE_POLICY,
                missing_operand="item",
            )
        return CanonicalDirective(
            kind=DirectiveKind.REMOVE_POLICY,
            operands=MappingProxyType({"item": item}),
        )

    return _invalid_directive_syntax(DirectiveSyntaxFailure.MALFORMED_DIRECTIVE)


def get_directive_metadata() -> tuple[DirectiveMetadata, ...]:
    """Return immutable public directive metadata derived from internal specs."""

    return _PUBLIC_DIRECTIVE_METADATA


def _serialize_canonical_directive(
    kind: DirectiveKind | str, operands: MappingProxyType[str, str]
) -> str:
    """Serialize a validated semantic directive without reparsing it."""
    normalized_kind = _normalize_directive_kind(kind)
    spec = _DIRECTIVE_SPECS[normalized_kind]

    return spec.renderer(operands)


def _render_directive(kind: DirectiveKind | str, /, **operands: str) -> str:
    """Produce canonical directive text from a semantic kind and operands."""
    normalized_kind = _normalize_directive_kind(kind)
    return CanonicalDirective(
        kind=normalized_kind,
        operands=MappingProxyType(dict(operands)),
    ).text


__all__ = [
    "DirectiveKind",
    "DirectiveSyntaxFailure",
    "DirectiveMetadata",
    "CanonicalDirective",
    "InvalidDirectiveSyntax",
    "get_directive_metadata",
    "decompose_directive",
]
