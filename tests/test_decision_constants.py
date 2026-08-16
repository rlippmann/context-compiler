import pytest

from context_compiler import (
    DECISION_ERROR,
    DECISION_NO_DIRECTIVE,
    DECISION_UPDATE,
    POLICY_PROHIBIT,
    POLICY_USE,
    DecisionKind,
    NoDirectiveDecision,
    SemanticErrorDecision,
    SemanticFailure,
    UpdateDecision,
)
from context_compiler.decision import _format_failure
from context_compiler.grammar import CanonicalDirective, DirectiveKind

pytestmark = pytest.mark.contract


def test_decision_constants_match_decision_kind_literals() -> None:
    assert DECISION_NO_DIRECTIVE == "no_directive"
    assert DECISION_UPDATE == "update"
    assert DECISION_ERROR == "error"
    assert DecisionKind.NO_DIRECTIVE == DECISION_NO_DIRECTIVE
    assert DecisionKind.UPDATE == DECISION_UPDATE
    assert DecisionKind.ERROR == DECISION_ERROR


def test_policy_constants_match_policy_literals() -> None:
    assert POLICY_USE == "use"
    assert POLICY_PROHIBIT == "prohibit"


def test_decision_variants_are_immutable_and_slotted() -> None:
    no_directive = NoDirectiveDecision()
    update = UpdateDecision(changed=True)
    error = SemanticErrorDecision(
        failure=SemanticFailure.ITEM_PROHIBITED,
        directive=CanonicalDirective(
            kind=DirectiveKind.USE_ITEM,
            operands={"item": "docker"},
        ),
    )

    assert no_directive.kind is DecisionKind.NO_DIRECTIVE
    assert update.kind is DecisionKind.UPDATE
    assert update.changed is True
    assert error.kind is DecisionKind.ERROR
    assert error.failure is SemanticFailure.ITEM_PROHIBITED
    assert error.directive.kind is DirectiveKind.USE_ITEM
    assert error.repairs == ()
    assert (
        error.message == '"docker" is currently prohibited.\nRemove or replace it before using it.'
    )

    for decision in (no_directive, update, error):
        assert hasattr(type(decision), "__slots__")

    try:
        update.changed = False  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("Decision variants must be immutable")


def test_unhandled_semantic_failure_is_an_intentional_defensive_error() -> None:
    directive = CanonicalDirective(
        kind=DirectiveKind.USE_ITEM,
        operands={"item": "docker"},
    )

    with pytest.raises(AssertionError, match="Unhandled semantic failure"):
        _format_failure(object(), directive)  # type: ignore[arg-type]
