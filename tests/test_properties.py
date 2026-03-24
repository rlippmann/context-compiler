from hypothesis import assume, given
from hypothesis import strategies as st

from context_compiler import create_engine
from context_compiler.engine import State


def _run_sequence(inputs: list[str]) -> State:
    engine = create_engine()
    for item in inputs:
        engine.step(item)
    return engine.state


@given(st.lists(st.text(max_size=40), min_size=0, max_size=20))
def test_determinism_same_input_sequence_same_state(inputs: list[str]) -> None:
    assert _run_sequence(inputs) == _run_sequence(inputs)


@given(st.text(min_size=1, max_size=30))
def test_idempotent_use_item_is_update_and_stable_state(item: str) -> None:
    assume(" instead of " not in item)
    engine = create_engine()
    d1 = engine.step(f"use {item}")
    d2 = engine.step(f"use {item}")

    assert d1["kind"] == "update"
    assert d2["kind"] == "update"
    assert len(engine.state["policies"]) == 1


@given(st.text(min_size=1, max_size=30))
def test_idempotent_prohibit_item_is_update_and_stable_state(item: str) -> None:
    engine = create_engine()
    d1 = engine.step(f"prohibit {item}")
    d2 = engine.step(f"prohibit {item}")

    assert d1["kind"] == "update"
    assert d2["kind"] == "update"
    assert len(engine.state["policies"]) == 1


@given(st.lists(st.text(max_size=80), min_size=0, max_size=20))
def test_non_matching_inputs_can_remain_passthrough_only(inputs: list[str]) -> None:
    engine = create_engine()
    before = engine.state

    for text in inputs:
        decision = engine.step(f"please {text}")
        assert decision["kind"] == "passthrough"

    assert engine.state == before


@given(st.lists(st.text(max_size=50), min_size=0, max_size=30))
def test_passthrough_sequence_preserves_state_and_decision_kind(inputs: list[str]) -> None:
    engine = create_engine()
    before = engine.state

    for text in inputs:
        decision = engine.step(f"prefix {text}")
        assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
        assert engine.state == before


@given(st.text(min_size=1, max_size=30))
def test_contradiction_use_after_prohibit_always_clarifies(item: str) -> None:
    engine = create_engine()
    engine.step(f"prohibit {item}")
    before = engine.state

    decision = engine.step(f"use {item}")
    assert decision["kind"] == "clarify"
    assert engine.state == before


@given(st.text(min_size=1, max_size=30))
def test_contradiction_prohibit_after_use_always_clarifies(item: str) -> None:
    assume(" instead of " not in item)
    engine = create_engine()
    engine.step(f"use {item}")
    before = engine.state

    decision = engine.step(f"prohibit {item}")
    assert decision["kind"] == "clarify"
    assert engine.state == before
