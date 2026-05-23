from context_compiler import DECISION_CLARIFY, DECISION_PASSTHROUGH, DECISION_UPDATE


def test_decision_constants_match_decision_kind_literals() -> None:
    assert DECISION_PASSTHROUGH == "passthrough"
    assert DECISION_UPDATE == "update"
    assert DECISION_CLARIFY == "clarify"
