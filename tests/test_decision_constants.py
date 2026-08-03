from context_compiler import (
    DECISION_ERROR,
    DECISION_NO_DIRECTIVE,
    DECISION_UPDATE,
    POLICY_PROHIBIT,
    POLICY_USE,
    get_decision_state,
    get_error_message,
    is_error,
    is_no_directive,
    is_update,
)
from context_compiler.engine import Decision


def test_decision_constants_match_decision_kind_literals() -> None:
    assert DECISION_NO_DIRECTIVE == "no_directive"
    assert DECISION_UPDATE == "update"
    assert DECISION_ERROR == "error"


def test_policy_constants_match_policy_literals() -> None:
    assert POLICY_USE == "use"
    assert POLICY_PROHIBIT == "prohibit"


def test_decision_helpers_for_update_decision() -> None:
    decision: Decision = {
        "kind": DECISION_UPDATE,
        "state": {"premise": "concise replies", "policies": {}, "version": 2},
    }

    assert is_update(decision) is True
    assert is_error(decision) is False
    assert is_no_directive(decision) is False
    assert get_error_message(decision) is None
    assert get_decision_state(decision) == {
        "premise": "concise replies",
        "policies": {},
        "version": 2,
    }


def test_decision_helpers_for_error_decision() -> None:
    decision: Decision = {
        "kind": DECISION_ERROR,
        "message": "Use what item?",
    }

    assert is_update(decision) is False
    assert is_error(decision) is True
    assert is_no_directive(decision) is False
    assert get_error_message(decision) == "Use what item?"
    assert get_decision_state(decision) is None


def test_decision_helpers_for_no_directive_decision() -> None:
    decision: Decision = {"kind": DECISION_NO_DIRECTIVE}

    assert is_update(decision) is False
    assert is_error(decision) is False
    assert is_no_directive(decision) is True
    assert get_error_message(decision) is None
    assert get_decision_state(decision) is None
