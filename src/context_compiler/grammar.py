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
class _DirectiveSpec:
    kind: DirectiveKind
    operand_names: tuple[str, ...]
    matcher: re.Pattern[str] | None
    exact_text: str | None
    renderer: Callable[[MappingProxyType[str, str]], str]
    canonical_starts: tuple[tuple[str, bool], ...]


_SET_PREMISE_PREFIX = "set premise "
_CHANGE_PREMISE_PREFIX = "change premise to "
_USE_PREFIX = "use "
_PROHIBIT_PREFIX = "prohibit "
_REMOVE_POLICY_PREFIX = "remove policy "
_INSTEAD_OF_DELIMITER = " instead of "

_MATCH_SET_PREMISE = re.compile(r"^set premise (?!to\b)\S(?:.*\S)?$")
_MATCH_CHANGE_PREMISE = re.compile(r"^change premise to \S(?:.*\S)?$")
_MATCH_USE_ITEM = re.compile(r"^use (?!instead of(?:\s|$))(?!.*\sinstead of(?:\s|$))\S(?:.*\S)?$")
_MATCH_PROHIBIT_ITEM = re.compile(r"^prohibit \S(?:.*\S)?$")
_MATCH_REMOVE_POLICY = re.compile(r"^remove policy \S(?:.*\S)?$")
_MATCH_REPLACE_USE = re.compile(r"^use \S(?:.*\S)? instead of \S(?:.*\S)?$")

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
            matcher=_MATCH_SET_PREMISE,
            exact_text=None,
            renderer=_render_with_prefix(_SET_PREMISE_PREFIX, "value"),
            canonical_starts=((_SET_PREMISE_PREFIX.removesuffix(" "), True),),
        ),
        DirectiveKind.CHANGE_PREMISE: _DirectiveSpec(
            kind=DirectiveKind.CHANGE_PREMISE,
            operand_names=("value",),
            matcher=_MATCH_CHANGE_PREMISE,
            exact_text=None,
            renderer=_render_with_prefix(_CHANGE_PREMISE_PREFIX, "value"),
            canonical_starts=((_CHANGE_PREMISE_PREFIX.removesuffix(" "), True),),
        ),
        DirectiveKind.USE_ITEM: _DirectiveSpec(
            kind=DirectiveKind.USE_ITEM,
            operand_names=("item",),
            matcher=_MATCH_USE_ITEM,
            exact_text=None,
            renderer=_render_with_prefix(_USE_PREFIX, "item"),
            canonical_starts=(("use", True),),
        ),
        DirectiveKind.PROHIBIT_ITEM: _DirectiveSpec(
            kind=DirectiveKind.PROHIBIT_ITEM,
            operand_names=("item",),
            matcher=_MATCH_PROHIBIT_ITEM,
            exact_text=None,
            renderer=_render_with_prefix(_PROHIBIT_PREFIX, "item"),
            canonical_starts=((_PROHIBIT_PREFIX.removesuffix(" "), True),),
        ),
        DirectiveKind.REMOVE_POLICY: _DirectiveSpec(
            kind=DirectiveKind.REMOVE_POLICY,
            operand_names=("item",),
            matcher=_MATCH_REMOVE_POLICY,
            exact_text=None,
            renderer=_render_with_prefix(_REMOVE_POLICY_PREFIX, "item"),
            canonical_starts=((_REMOVE_POLICY_PREFIX.removesuffix(" "), True),),
        ),
        DirectiveKind.REPLACE_USE: _DirectiveSpec(
            kind=DirectiveKind.REPLACE_USE,
            operand_names=("new_item", "old_item"),
            matcher=_MATCH_REPLACE_USE,
            exact_text=None,
            renderer=_render_replace_use,
            canonical_starts=(("use", True),),
        ),
        DirectiveKind.CLEAR_PREMISE: _DirectiveSpec(
            kind=DirectiveKind.CLEAR_PREMISE,
            operand_names=(),
            matcher=None,
            exact_text="clear premise",
            renderer=_render_exact("clear premise"),
            canonical_starts=(("clear premise", False),),
        ),
        DirectiveKind.RESET_POLICIES: _DirectiveSpec(
            kind=DirectiveKind.RESET_POLICIES,
            operand_names=(),
            matcher=None,
            exact_text="reset policies",
            renderer=_render_exact("reset policies"),
            canonical_starts=(("reset policies", False),),
        ),
        DirectiveKind.CLEAR_STATE: _DirectiveSpec(
            kind=DirectiveKind.CLEAR_STATE,
            operand_names=(),
            matcher=None,
            exact_text="clear state",
            renderer=_render_exact("clear state"),
            canonical_starts=(("clear state", False),),
        ),
    }
)


def _match_canonical_directive_start(text: str, start: int) -> int | None:
    if start < 0 or start >= len(text):
        return None

    if start > 0 and text[start - 1].isalpha():
        return None

    for token, require_space_or_end in _CANONICAL_DIRECTIVE_STARTS:
        if not text.startswith(token, start):
            continue
        end = start + len(token)
        if end == len(text):
            return end
        next_char = text[end]
        if require_space_or_end:
            if next_char == " ":
                return end
            continue
        if not next_char.isalpha():
            return end

    return None


def _contains_multiple_canonical_directives(text: str) -> bool:
    first_start = _match_canonical_directive_start(text, 0)
    if first_start is None:
        return False

    for index in range(first_start, len(text)):
        next_start = _match_canonical_directive_start(text, index)
        if next_start is not None:
            return True

    return False


def validate_directive(text: str) -> ValidatedDirective | None:
    if text == "":
        return None
    if _contains_multiple_canonical_directives(text):
        return None

    for kind, spec in _DIRECTIVE_SPECS.items():
        if spec.exact_text is not None:
            if text == spec.exact_text:
                return ValidatedDirective(text=text, kind=kind)
            continue
        assert spec.matcher is not None
        if spec.matcher.fullmatch(text):
            return ValidatedDirective(text=text, kind=kind)

    return None


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
