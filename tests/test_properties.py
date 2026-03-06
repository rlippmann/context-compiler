from __future__ import annotations

import re

from hypothesis import assume, given
from hypothesis import strategies as st

from context_compiler import create_engine
from context_compiler.engine import State, _has_multiple_values, _split_items


def _run_sequence(inputs: list[str]) -> State:
    engine = create_engine()
    for item in inputs:
        engine.step(item)
    return engine.state


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


@given(st.lists(st.text(max_size=40), min_size=0, max_size=20))
def test_determinism_same_input_sequence_same_state(inputs: list[str]) -> None:
    assert _run_sequence(inputs) == _run_sequence(inputs)


@given(st.text(min_size=1, max_size=30))
def test_policy_addition_is_idempotent(item: str) -> None:
    engine = create_engine()

    engine.step(f"avoid {item}")
    once = list(engine.state["policies"]["prohibit"])

    engine.step(f"avoid {item}")
    twice = list(engine.state["policies"]["prohibit"])

    assert twice == once


@given(
    st.from_regex(r"[A-Za-z0-9][A-Za-z0-9 ]{0,20}", fullmatch=True),
    st.from_regex(r"[A-Za-z0-9][A-Za-z0-9 ]{0,20}", fullmatch=True),
)
def test_exclusive_fact_replacement_last_write_wins(first: str, second: str) -> None:
    assume(" and " not in first.lower() and "," not in first)
    assume(" and " not in second.lower() and "," not in second)

    engine = create_engine()

    engine.step(f"use {first}")
    engine.step(f"use {second}")

    assert engine.state["facts"]["focus.device"] == _clean(second)


@given(
    st.sampled_from(
        [
            "don use parallel octaves",
            "dnot use docker",
            "i using nord",
            "allow",
            "set",
            "no use docker",
            "do n't use x",
            "use and set",
        ]
    )
)
def test_safety_near_miss_inputs_do_not_mutate_state(text: str) -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step(text)

    assert decision["kind"] != "update"
    assert engine.state == before


@given(st.from_regex(r"[a-z]{1,10}-and-[a-z]{1,10}", fullmatch=True))
def test_hyphenated_and_token_not_split(token: str) -> None:
    engine = create_engine()

    decision = engine.step(f"avoid {token}")

    assert decision["kind"] == "update"
    assert engine.state["policies"]["prohibit"] == [token]


@given(st.from_regex(r"[A-Za-z0-9][A-Za-z0-9 ]{0,20}", fullmatch=True))
def test_please_use_is_not_a_supported_positive_directive(value: str) -> None:
    assume("," not in value)
    assume(" and " not in value.lower())

    engine = create_engine()
    before = engine.state
    decision = engine.step(f"please use {value}")

    assert decision["kind"] != "update"
    assert engine.state == before


@given(st.text(max_size=80))
def test_split_and_has_multiple_values_are_consistent(text: str) -> None:
    non_empty = [item for item in _split_items(text) if item]
    assert _has_multiple_values(text) == (len(non_empty) > 1)
