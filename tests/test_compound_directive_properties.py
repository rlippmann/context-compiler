import string

from _decision_test_helpers import assert_decision
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from context_compiler import (
    DECISION_NO_DIRECTIVE,
    Engine,
)
from context_compiler.grammar import InvalidDirectiveSyntax, decompose_directive

CANONICAL_SECOND_DIRECTIVES = [
    "set premise concise",
    "change premise to concise",
    "use pytest",
    "prohibit peanuts",
    "remove policy docker",
    "use pytest instead of docker",
    "clear premise",
    "reset policies",
    "clear state",
]

CANONICAL_STARTS = [
    "set premise",
    "change premise to",
    "use",
    "prohibit",
    "remove policy",
    "clear premise",
    "reset policies",
    "clear state",
]

SEPARATOR_CHARS = " \t\n\r,.;:!?-/()[]"
LETTER_CHARS = string.ascii_lowercase


def _observations(engine: object) -> tuple[object, object]:
    return engine.premise, dict(engine.policies)


def _assert_compound_no_directive(user_input: str) -> None:
    engine = Engine()
    before = _observations(engine)

    decision = engine.step(user_input)

    assert_decision(decision, {"kind": DECISION_NO_DIRECTIVE})
    assert _observations(engine) == before


@settings(max_examples=50)
@given(
    separator=st.text(alphabet=SEPARATOR_CHARS, min_size=1, max_size=8),
    second=st.sampled_from(CANONICAL_SECOND_DIRECTIVES),
)
def test_compound_separator_robustness(separator: str, second: str) -> None:
    user_input = f"use docker{separator}{second}"
    assert isinstance(decompose_directive(user_input), InvalidDirectiveSyntax)
    _assert_compound_no_directive(user_input)


@settings(max_examples=50)
@given(
    chunks=st.lists(
        st.text(alphabet=LETTER_CHARS + " -_", min_size=1, max_size=8),
        min_size=1,
        max_size=3,
    ),
    second=st.sampled_from(CANONICAL_SECOND_DIRECTIVES),
)
def test_compound_arbitrary_intervening_text(chunks: list[str], second: str) -> None:
    intervening = " ".join(chunks)
    lowered = intervening.lower()
    assume(all(token not in lowered for token in CANONICAL_STARTS))

    user_input = f"use docker {intervening} {second}"
    assert isinstance(decompose_directive(user_input), InvalidDirectiveSyntax)
    _assert_compound_no_directive(user_input)


@settings(max_examples=50)
@given(
    token=st.sampled_from(CANONICAL_STARTS),
    prefix=st.text(alphabet=LETTER_CHARS, min_size=1, max_size=4),
    suffix=st.text(alphabet=LETTER_CHARS, min_size=1, max_size=4),
)
def test_embedded_canonical_tokens_do_not_trigger_compound_detection(
    token: str, prefix: str, suffix: str
) -> None:
    engine = Engine()
    before = _observations(engine)

    user_input = f"use docker {prefix}{token}{suffix}"
    parsed = decompose_directive(user_input)
    decision = engine.step(user_input)

    assert parsed is not None
    assert not isinstance(parsed, InvalidDirectiveSyntax)
    assert_decision(decision, {"kind": "update"})
    assert _observations(engine) != before


@settings(max_examples=50)
@given(
    prefix=st.text(
        alphabet=st.characters(blacklist_characters="\n\r"),
        min_size=1,
        max_size=20,
    ),
    second=st.sampled_from(CANONICAL_SECOND_DIRECTIVES),
)
def test_leading_non_directive_text_disables_compound_detection(prefix: str, second: str) -> None:
    assume(not any(prefix.startswith(token) for token in CANONICAL_STARTS))

    engine = Engine()
    before = _observations(engine)
    decision = engine.step(f"{prefix} use docker {second}")

    assert_decision(decision, {"kind": DECISION_NO_DIRECTIVE})
    assert _observations(engine) == before


def _mutate_case(text: str) -> st.SearchStrategy[str]:
    alpha_indexes = [index for index, char in enumerate(text) if char.isalpha()]
    return st.sampled_from(alpha_indexes).map(
        lambda index: text[:index] + text[index].upper() + text[index + 1 :],
    )


@settings(max_examples=50)
@given(second_start=st.sampled_from(CANONICAL_STARTS).flatmap(_mutate_case))
def test_case_mutated_second_directive_does_not_trigger_compound_detection(
    second_start: str,
) -> None:
    engine = Engine()
    before = _observations(engine)

    user_input = f"use docker {second_start}"
    assert isinstance(decompose_directive(user_input), InvalidDirectiveSyntax)
    decision = engine.step(user_input)

    assert_decision(decision, {"kind": DECISION_NO_DIRECTIVE})
    assert _observations(engine) == before


@settings(max_examples=50)
@given(
    quote=st.sampled_from(['"', "'"]),
    payload=st.text(
        alphabet=LETTER_CHARS + " \t,.;:-",
        min_size=0,
        max_size=12,
    ),
    closing=st.sampled_from(["", '"', "'"]),
    second=st.sampled_from(CANONICAL_SECOND_DIRECTIVES),
)
def test_quotes_do_not_create_protected_region_after_first_directive(
    quote: str, payload: str, closing: str, second: str
) -> None:
    user_input = f"use {quote}{payload}{closing} {second}"
    assert isinstance(decompose_directive(user_input), InvalidDirectiveSyntax)
    _assert_compound_no_directive(user_input)


@settings(max_examples=20)
@given(
    quote=st.sampled_from(['"', "'"]),
    second=st.sampled_from(CANONICAL_SECOND_DIRECTIVES),
)
def test_fully_quoted_input_remains_no_directive(quote: str, second: str) -> None:
    engine = Engine()
    before = _observations(engine)

    decision = engine.step(f"{quote}use docker {second}{quote}")

    assert_decision(decision, {"kind": DECISION_NO_DIRECTIVE})
    assert _observations(engine) == before
