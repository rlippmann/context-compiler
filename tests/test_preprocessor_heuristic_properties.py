import re

from hypothesis import assume, given
from hypothesis import strategies as st

from experimental.preprocessor.constants import (
    PRECOMPILE_OUTCOME_DIRECTIVE,
    PRECOMPILE_OUTCOME_NO_DIRECTIVE,
    PRECOMPILE_OUTCOME_UNKNOWN,
)
from experimental.preprocessor.heuristic_preprocessor import precompile_heuristic
from experimental.preprocessor.output_validation import (
    _is_allowed_directive,
    parse_preprocessor_output,
)

CANONICAL_DIRECTIVES = [
    "set premise concise replies",
    "change premise to formal tone",
    "use docker",
    "prohibit peanuts",
    "remove policy docker",
    "use podman instead of docker",
    "clear premise",
    "reset policies",
    "clear state",
]

NON_EMPTY_TEXT = st.text(min_size=1, max_size=40).filter(lambda s: s.strip() != "")
WRAPPERS = st.sampled_from(
    [
        ("(", ")"),
        ("[", "]"),
    ]
)
QUOTED_WRAPPERS = st.sampled_from(
    [
        ('"', '"'),
        ("'", "'"),
        ("`", "`"),
    ]
)


@given(st.sampled_from(CANONICAL_DIRECTIVES), st.sampled_from([".", "!"]))
def test_heuristic_accepts_canonical_directive_with_trailing_period_or_bang(
    directive: str, punctuation: str
) -> None:
    result = precompile_heuristic(f"{directive}{punctuation}")
    assert result["outcome"] == PRECOMPILE_OUTCOME_DIRECTIVE
    parsed = parse_preprocessor_output(result["directive"])
    assert parsed == result["directive"]


@given(st.sampled_from(CANONICAL_DIRECTIVES))
def test_heuristic_question_suffix_never_produces_directive(directive: str) -> None:
    result = precompile_heuristic(f"{directive}?")
    assert result["outcome"] == PRECOMPILE_OUTCOME_UNKNOWN
    assert result["directive"] is None


@given(st.sampled_from(CANONICAL_DIRECTIVES), WRAPPERS)
def test_heuristic_accepts_single_layer_exact_wrapper(
    directive: str, wrapper: tuple[str, str]
) -> None:
    left, right = wrapper
    result = precompile_heuristic(f"{left}{directive}{right}")
    assert result["outcome"] == PRECOMPILE_OUTCOME_DIRECTIVE
    parsed = parse_preprocessor_output(result["directive"])
    assert parsed == result["directive"]


@given(st.sampled_from(CANONICAL_DIRECTIVES), QUOTED_WRAPPERS)
def test_heuristic_quoted_exact_wrappers_never_directive(
    directive: str, wrapper: tuple[str, str]
) -> None:
    left, right = wrapper
    result = precompile_heuristic(f"{left}{directive}{right}")
    assert result["outcome"] == PRECOMPILE_OUTCOME_UNKNOWN
    assert result["directive"] is None


@given(
    st.sampled_from(CANONICAL_DIRECTIVES),
    WRAPPERS,
    st.sampled_from(["example:", "for example", "i said", "he said", "the command is"]),
)
def test_heuristic_rejects_wrapped_directive_with_surrounding_meta_text(
    directive: str, wrapper: tuple[str, str], prefix: str
) -> None:
    left, right = wrapper
    message = f"{prefix} {left}{directive}{right}"
    result = precompile_heuristic(message)
    assert result["outcome"] != PRECOMPILE_OUTCOME_DIRECTIVE


@given(st.text(max_size=60), st.text(max_size=60))
def test_heuristic_question_mark_is_always_rejected(prefix: str, suffix: str) -> None:
    message = f"{prefix}?{suffix}"
    result = precompile_heuristic(message)
    assert result["outcome"] in {PRECOMPILE_OUTCOME_NO_DIRECTIVE, PRECOMPILE_OUTCOME_UNKNOWN}
    assert result["directive"] is None


@given(st.text(max_size=120))
def test_heuristic_directive_output_is_always_validator_safe(message: str) -> None:
    result = precompile_heuristic(message)
    if result["outcome"] != PRECOMPILE_OUTCOME_DIRECTIVE:
        return
    directive = result["directive"]
    assert isinstance(directive, str)
    assert parse_preprocessor_output(directive) == directive


@given(st.sampled_from(CANONICAL_DIRECTIVES), NON_EMPTY_TEXT, NON_EMPTY_TEXT)
def test_heuristic_whole_message_discipline_for_surrounded_directive(
    directive: str, prefix: str, suffix: str
) -> None:
    message = f"{prefix} {directive} {suffix}"
    normalized = re.sub(r"\s+", " ", message.strip().lower())
    assume(prefix.strip() not in {'"', "'", "`", "(", "["})
    assume(suffix.strip() not in {'"', "'", "`", ")", "]"})
    assume(not message.strip().lower().startswith("change premise "))
    assume(not _is_allowed_directive(normalized))
    result = precompile_heuristic(message)
    assert result["outcome"] != PRECOMPILE_OUTCOME_DIRECTIVE


@given(NON_EMPTY_TEXT)
def test_heuristic_list_or_enumeration_prefix_never_directive(rest: str) -> None:
    for prefix in ("1. ", "- ", "* "):
        result = precompile_heuristic(f"{prefix}{rest}")
        assert result["outcome"] != PRECOMPILE_OUTCOME_DIRECTIVE


@given(st.sampled_from(CANONICAL_DIRECTIVES))
def test_heuristic_meta_reporting_prefix_never_directive(directive: str) -> None:
    samples = [
        f"example: {directive}",
        f"for example {directive}",
        f"the command is {directive}",
        f'i said "{directive}"',
        f'he said "{directive}"',
    ]
    for message in samples:
        result = precompile_heuristic(message)
        assert result["outcome"] != PRECOMPILE_OUTCOME_DIRECTIVE


@given(st.sampled_from(["use docker", "clear state", "prohibit peanuts"]), NON_EMPTY_TEXT)
def test_heuristic_mixed_prose_connector_forms_never_directive(
    directive_seed: str, detail: str
) -> None:
    messages = [
        f"{directive_seed} because {detail}",
        f"{directive_seed} then continue {detail}",
        f"{directive_seed} and {detail}",
    ]
    for message in messages:
        result = precompile_heuristic(message)
        assert result["outcome"] != PRECOMPILE_OUTCOME_DIRECTIVE
