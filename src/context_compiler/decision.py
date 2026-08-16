"""Immutable domain results returned by the context compiler engine."""

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Literal, TypeAlias
from unicodedata import normalize as unicode_normalize

from .const import DECISION_ERROR, DECISION_NO_DIRECTIVE, DECISION_UPDATE
from .grammar import CanonicalDirective


class DecisionKind(StrEnum):
    """Stable discriminator for engine evaluation results."""

    NO_DIRECTIVE = DECISION_NO_DIRECTIVE
    UPDATE = DECISION_UPDATE
    ERROR = DECISION_ERROR


class SemanticFailure(StrEnum):
    """Machine-readable classifications for semantic directive failures."""

    PREMISE_ALREADY_SET = "premise_already_set"
    PREMISE_NOT_SET = "premise_not_set"
    ITEM_PROHIBITED = "item_prohibited"
    ITEM_ALREADY_IN_USE = "item_already_in_use"
    REPLACEMENT_SOURCE_PROHIBITED = "replacement_source_prohibited"
    REPLACEMENT_TARGET_PROHIBITED = "replacement_target_prohibited"
    REPLACEMENT_SOURCE_MISSING = "replacement_source_missing"


@dataclass(frozen=True, slots=True)
class NoDirectiveDecision:
    """No usable canonical directive was produced from the input."""

    kind: ClassVar[Literal[DecisionKind.NO_DIRECTIVE]] = DecisionKind.NO_DIRECTIVE


@dataclass(frozen=True, slots=True)
class UpdateDecision:
    """A canonical directive was accepted and evaluated."""

    changed: bool
    kind: ClassVar[Literal[DecisionKind.UPDATE]] = DecisionKind.UPDATE


@dataclass(frozen=True, slots=True)
class SemanticErrorDecision:
    """A canonical directive was rejected during semantic evaluation."""

    failure: SemanticFailure
    directive: CanonicalDirective
    repairs: tuple[CanonicalDirective, ...] = ()
    kind: ClassVar[Literal[DecisionKind.ERROR]] = DecisionKind.ERROR

    @property
    def message(self) -> str:
        """Return deterministic human-readable text for this semantic failure."""

        return _format_failure(self.failure, self.directive)


Decision: TypeAlias = NoDirectiveDecision | UpdateDecision | SemanticErrorDecision


def _format_failure(failure: SemanticFailure, directive: CanonicalDirective) -> str:
    if failure is SemanticFailure.PREMISE_ALREADY_SET:
        return "Premise already set.\nUse 'change premise to <value>' to modify it."

    if failure is SemanticFailure.PREMISE_NOT_SET:
        return "No premise is set.\nUse 'set premise <value>' to define one."

    if failure is SemanticFailure.ITEM_PROHIBITED:
        item_key = _normalize_item(directive.operands["item"])
        return f'"{item_key}" is currently prohibited.\nRemove or replace it before using it.'

    if failure is SemanticFailure.ITEM_ALREADY_IN_USE:
        item_key = _normalize_item(directive.operands["item"])
        return f'"{item_key}" is currently in use.\nRemove or replace it before prohibiting it.'

    if failure is SemanticFailure.REPLACEMENT_SOURCE_PROHIBITED:
        old_item = directive.operands["old_item"]
        return (
            f'"{old_item}" is currently prohibited.\n'
            "Submit explicit directive(s) to remove it or use a different item."
        )

    if failure is SemanticFailure.REPLACEMENT_TARGET_PROHIBITED:
        new_item = directive.operands["new_item"]
        return (
            f'"{new_item}" is currently prohibited.\n'
            "Submit explicit directive(s) to remove it or use a different item."
        )

    if failure is SemanticFailure.REPLACEMENT_SOURCE_MISSING:
        old_item = directive.operands["old_item"]
        return (
            f"\"{old_item}\" is not currently in use.\nReplacement requires an active 'use' policy."
        )

    raise AssertionError(f"Unhandled semantic failure: {failure!r}")


def _normalize_item(value: str) -> str:
    normalized = unicode_normalize("NFKC", value)
    normalized = normalized.replace("’", "'").replace("`", "'")
    return " ".join(normalized.casefold().split())
