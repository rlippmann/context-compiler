from context_compiler import (
    DECISION_CLARIFY,
    DECISION_PASSTHROUGH,
    DECISION_UPDATE,
    POLICY_PROHIBIT,
    POLICY_USE,
    get_clarify_prompt,
    get_decision_state,
    is_clarify,
    is_passthrough,
    is_update,
)
from context_compiler.engine import Decision


def test_decision_constants_match_decision_kind_literals() -> None:
    assert DECISION_PASSTHROUGH == "passthrough"
    assert DECISION_UPDATE == "update"
    assert DECISION_CLARIFY == "clarify"


def test_policy_constants_match_policy_literals() -> None:
    assert POLICY_USE == "use"
    assert POLICY_PROHIBIT == "prohibit"


def test_decision_helpers_for_update_decision() -> None:
    decision: Decision = {
        "kind": DECISION_UPDATE,
        "state": {"premise": "concise replies", "policies": {}, "version": 2},
        "prompt_to_user": None,
    }

    assert is_update(decision) is True
    assert is_clarify(decision) is False
    assert is_passthrough(decision) is False
    assert get_clarify_prompt(decision) is None
    assert get_decision_state(decision) == {
        "premise": "concise replies",
        "policies": {},
        "version": 2,
    }


def test_decision_helpers_for_clarify_decision() -> None:
    decision: Decision = {
        "kind": DECISION_CLARIFY,
        "state": None,
        "prompt_to_user": "Use what item?",
    }

    assert is_update(decision) is False
    assert is_clarify(decision) is True
    assert is_passthrough(decision) is False
    assert get_clarify_prompt(decision) == "Use what item?"
    assert get_decision_state(decision) is None


def test_decision_helpers_for_passthrough_decision() -> None:
    decision: Decision = {
        "kind": DECISION_PASSTHROUGH,
        "state": None,
        "prompt_to_user": None,
    }

    assert is_update(decision) is False
    assert is_clarify(decision) is False
    assert is_passthrough(decision) is True
    assert get_clarify_prompt(decision) is None
    assert get_decision_state(decision) is None
