from collections.abc import Mapping

from context_compiler import (
    DECISION_ERROR,
    DECISION_NO_DIRECTIVE,
    DECISION_UPDATE,
    Decision,
    SemanticErrorDecision,
    UpdateDecision,
)


def assert_decision(decision: Decision, expected: Mapping[str, object]) -> None:
    """Compare a domain decision with a legacy-shaped fixture expectation."""

    assert decision.kind == expected["kind"]
    if decision.kind == DECISION_UPDATE:
        assert isinstance(decision, UpdateDecision)
        if "changed" in expected:
            assert decision.changed is expected["changed"]
    elif decision.kind == DECISION_ERROR:
        assert isinstance(decision, SemanticErrorDecision)
        assert decision.message == expected["message"]
    else:
        assert decision.kind == DECISION_NO_DIRECTIVE


def decision_observation(decision: Decision) -> dict[str, object]:
    """Adapt a domain result for existing fixture assertions."""

    message = decision.message if isinstance(decision, SemanticErrorDecision) else None
    return {"kind": decision.kind, "message": message}
