from hypothesis import given
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


@given(st.lists(st.text(max_size=80), min_size=0, max_size=20))
def test_passthrough_only_inputs_do_not_mutate_state(inputs: list[str]) -> None:
    engine = create_engine()
    before = engine.state

    for text in inputs:
        decision = engine.step(text)
        assert decision["kind"] == "passthrough"

    assert engine.state == before
