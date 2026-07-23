"""Immutable canonical grammar helpers for Context Compiler directives."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class DirectiveKind(StrEnum):
    SET_PREMISE = "set_premise"
    CHANGE_PREMISE = "change_premise"
    USE_ITEM = "use_item"
    PROHIBIT_ITEM = "prohibit_item"
    REMOVE_POLICY = "remove_policy"
    REPLACE_USE = "replace_use"
    CLEAR_PREMISE = "clear_premise"
    RESET_POLICIES = "reset_policies"
    CLEAR_STATE = "clear_state"


@dataclass(frozen=True, slots=True)
class ValidatedDirective:
    text: str
    kind: DirectiveKind


@dataclass(frozen=True, slots=True)
class _ParsedDirective:
    text: str
    kind: DirectiveKind
    operands: MappingProxyType[str, str]


@dataclass(frozen=True, slots=True)
class _DirectiveSpec:
    kind: DirectiveKind
    operand_names: tuple[str, ...]
    exact_text: str | None
    renderer: Callable[[MappingProxyType[str, str]], str]


_SET_PREMISE_PREFIX = "set premise "
_CHANGE_PREMISE_PREFIX = "change premise to "
_USE_PREFIX = "use "
_PROHIBIT_PREFIX = "prohibit "
_REMOVE_POLICY_PREFIX = "remove policy "
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

_CANONICAL_DIRECTIVE_STARTS: tuple[tuple[str, bool], ...] = (
    (_CHANGE_PREMISE_PREFIX.removesuffix(" "), True),
    (_SET_PREMISE_PREFIX.removesuffix(" "), True),
    (_REMOVE_POLICY_PREFIX.removesuffix(" "), True),
    ("reset policies", False),
    ("clear premise", False),
    ("clear state", False),
    (_PROHIBIT_PREFIX.removesuffix(" "), True),
    ("use", True),
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
            operand_names=("value",),
            exact_text=None,
            renderer=_render_with_prefix(_SET_PREMISE_PREFIX, "value"),
        ),
        DirectiveKind.CHANGE_PREMISE: _DirectiveSpec(
            kind=DirectiveKind.CHANGE_PREMISE,
            operand_names=("value",),
            exact_text=None,
            renderer=_render_with_prefix(_CHANGE_PREMISE_PREFIX, "value"),
        ),
        DirectiveKind.USE_ITEM: _DirectiveSpec(
            kind=DirectiveKind.USE_ITEM,
            operand_names=("item",),
            exact_text=None,
            renderer=_render_with_prefix(_USE_PREFIX, "item"),
        ),
        DirectiveKind.PROHIBIT_ITEM: _DirectiveSpec(
            kind=DirectiveKind.PROHIBIT_ITEM,
            operand_names=("item",),
            exact_text=None,
            renderer=_render_with_prefix(_PROHIBIT_PREFIX, "item"),
        ),
        DirectiveKind.REMOVE_POLICY: _DirectiveSpec(
            kind=DirectiveKind.REMOVE_POLICY,
            operand_names=("item",),
            exact_text=None,
            renderer=_render_with_prefix(_REMOVE_POLICY_PREFIX, "item"),
        ),
        DirectiveKind.REPLACE_USE: _DirectiveSpec(
            kind=DirectiveKind.REPLACE_USE,
            operand_names=("new_item", "old_item"),
            exact_text=None,
            renderer=_render_replace_use,
        ),
        DirectiveKind.CLEAR_PREMISE: _DirectiveSpec(
            kind=DirectiveKind.CLEAR_PREMISE,
            operand_names=(),
            exact_text="clear premise",
            renderer=_render_exact("clear premise"),
        ),
        DirectiveKind.RESET_POLICIES: _DirectiveSpec(
            kind=DirectiveKind.RESET_POLICIES,
            operand_names=(),
            exact_text="reset policies",
            renderer=_render_exact("reset policies"),
        ),
        DirectiveKind.CLEAR_STATE: _DirectiveSpec(
            kind=DirectiveKind.CLEAR_STATE,
            operand_names=(),
            exact_text="clear state",
            renderer=_render_exact("clear state"),
        ),
    }
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

        if text[index].casefold() != token_char:
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
    first_start = _match_canonical_directive_start(text, 0)
    if first_start is None:
        return False

    for index in range(first_start, len(text)):
        next_start = _match_canonical_directive_start(text, index)
        if next_start is not None:
            return True

    return False


def _parse_replace_use(trimmed_text: str) -> _ParsedDirective | None:
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
    return _ParsedDirective(
        text=trimmed_text,
        kind=DirectiveKind.REPLACE_USE,
        operands=MappingProxyType({"new_item": new_item, "old_item": old_item}),
    )


def _parse_directive(text: str) -> _ParsedDirective | None:
    trimmed_text = _trim_ascii_whitespace(text)
    if trimmed_text == "":
        return None
    if _contains_multiple_canonical_directives(trimmed_text):
        return None

    normalized = _normalized_for_matching(trimmed_text)

    if normalized == "clear premise":
        return _ParsedDirective(
            text=text, kind=DirectiveKind.CLEAR_PREMISE, operands=MappingProxyType({})
        )
    if normalized == "reset policies":
        return _ParsedDirective(
            text=text,
            kind=DirectiveKind.RESET_POLICIES,
            operands=MappingProxyType({}),
        )
    if normalized == "clear state":
        return _ParsedDirective(
            text=text, kind=DirectiveKind.CLEAR_STATE, operands=MappingProxyType({})
        )

    if normalized.startswith("set premise "):
        match = _SET_PREMISE_RE.fullmatch(trimmed_text)
        if match is None:
            return None
        value = match.group("value")
        if not _operand_has_content(value) or _operand_starts_with_token(value, "to"):
            return None
        return _ParsedDirective(
            text=text,
            kind=DirectiveKind.SET_PREMISE,
            operands=MappingProxyType({"value": value}),
        )

    if normalized.startswith("change premise to "):
        match = _CHANGE_PREMISE_RE.fullmatch(trimmed_text)
        if match is None:
            return None
        value = match.group("value")
        if not _operand_has_content(value):
            return None
        return _ParsedDirective(
            text=text,
            kind=DirectiveKind.CHANGE_PREMISE,
            operands=MappingProxyType({"value": value}),
        )

    replacement = _parse_replace_use(trimmed_text)
    if replacement is not None:
        return replacement

    if normalized.startswith("use "):
        match = _USE_RE.fullmatch(trimmed_text)
        if match is None:
            return None
        item = match.group("item")
        normalized_item = _normalized_for_matching(item)
        if (
            not _operand_has_content(item)
            or normalized_item.startswith("instead of ")
            or normalized_item.endswith(" instead of")
            or _INSTEAD_OF_DELIMITER in normalized_item
        ):
            return None
        return _ParsedDirective(
            text=text,
            kind=DirectiveKind.USE_ITEM,
            operands=MappingProxyType({"item": item}),
        )

    if normalized.startswith("prohibit "):
        match = _PROHIBIT_RE.fullmatch(trimmed_text)
        if match is None:
            return None
        item = match.group("item")
        if not _operand_has_content(item):
            return None
        return _ParsedDirective(
            text=text,
            kind=DirectiveKind.PROHIBIT_ITEM,
            operands=MappingProxyType({"item": item}),
        )

    if normalized.startswith("remove policy "):
        match = _REMOVE_POLICY_RE.fullmatch(trimmed_text)
        if match is None:
            return None
        item = match.group("item")
        if not _operand_has_content(item):
            return None
        return _ParsedDirective(
            text=text,
            kind=DirectiveKind.REMOVE_POLICY,
            operands=MappingProxyType({"item": item}),
        )

    return None


def validate_directive(text: str) -> ValidatedDirective | None:
    parsed = _parse_directive(text)
    if parsed is None:
        return None
    return ValidatedDirective(text=parsed.text, kind=parsed.kind)


def is_canonical_directive(text: str) -> bool:
    return validate_directive(text) is not None


def render_directive(kind: DirectiveKind, /, **operands: str) -> str:
    try:
        normalized_kind = kind if isinstance(kind, DirectiveKind) else DirectiveKind(kind)
        spec = _DIRECTIVE_SPECS[normalized_kind]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Unsupported directive kind: {kind!r}") from exc

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
        if raw_value.strip() == "":
            raise ValueError(f"Operand {name!r} for {kind.value} cannot be empty.")
        normalized_operands[name] = raw_value

    operand_view = MappingProxyType(normalized_operands)
    rendered = spec.renderer(operand_view)
    validated = validate_directive(rendered)
    if validated is None or validated.kind is not normalized_kind:
        raise ValueError(f"Operands do not produce a canonical {normalized_kind.value} directive.")
    return rendered


__all__ = [
    "DirectiveKind",
    "ValidatedDirective",
    "is_canonical_directive",
    "render_directive",
    "validate_directive",
]
