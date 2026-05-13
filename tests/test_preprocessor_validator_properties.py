from hypothesis import assume, given
from hypothesis import strategies as st

from experimental.preprocessor.output_validation import (
    _is_allowed_directive,
    parse_preprocessor_output,
    validate_preprocessor_output,
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

SPACE_TEXT = st.text(alphabet=" \t\n", min_size=0, max_size=4)
NON_EMPTY_TEXT = st.text(min_size=1, max_size=40).filter(lambda s: s.strip() != "")

NOISY_TEXT = st.one_of(
    st.text(min_size=0, max_size=80),
    st.builds(lambda a, b: f"{a}\n{b}", st.text(max_size=40), st.text(max_size=40)),
    st.builds(lambda t: f'"{t}"', st.text(max_size=60)),
    st.builds(lambda t: f"`{t}`", st.text(max_size=60)),
    st.builds(lambda t: f"[{t}]", st.text(max_size=60)),
    st.builds(lambda a, b: f"{a}; {b}", st.text(max_size=30), st.text(max_size=30)),
    st.builds(lambda a, b: f"{a}: {b}", st.text(max_size=30), st.text(max_size=30)),
)


@given(
    st.one_of(
        st.none(),
        st.integers(),
        st.floats(),
        st.booleans(),
        st.binary(),
        st.lists(st.integers()),
        st.dictionaries(st.text(max_size=10), st.integers()),
    )
)
def test_parse_non_string_never_produces_directive(raw_output: object) -> None:
    assert parse_preprocessor_output(raw_output) is None


@given(NOISY_TEXT)
def test_parse_invalid_text_never_becomes_directive(text: str) -> None:
    stripped = text.strip()
    assume(not _is_allowed_directive(stripped))
    assert parse_preprocessor_output(text) is None


@given(st.sampled_from(CANONICAL_DIRECTIVES), SPACE_TEXT, SPACE_TEXT)
def test_parse_valid_canonical_directive_always_passes(
    directive: str, leading_ws: str, trailing_ws: str
) -> None:
    raw = f"{leading_ws}{directive}{trailing_ws}"
    assert parse_preprocessor_output(raw) == directive


@given(st.sampled_from(CANONICAL_DIRECTIVES), NON_EMPTY_TEXT, NON_EMPTY_TEXT)
def test_parse_rejects_directive_with_surrounding_text(
    directive: str, prefix: str, suffix: str
) -> None:
    raw = f"{prefix} {directive} {suffix}"
    stripped = raw.strip()
    assume(not _is_allowed_directive(stripped))
    assert parse_preprocessor_output(raw) is None


@given(
    st.sampled_from(CANONICAL_DIRECTIVES),
    st.sampled_from(
        [
            'example: "{}"',
            "for example `{}`",
            "notes: [{}]",
            'he said "{}"',
            'command = "{}"',
        ]
    ),
)
def test_parse_rejects_directive_in_constrained_wrappers(directive: str, wrapper: str) -> None:
    wrapped = wrapper.format(directive)
    assert parse_preprocessor_output(wrapped) is None


def test_validate_malformed_abstain_negative_boundaries_are_unknown() -> None:
    cases = {
        "<NO_DIRECT>": "unknown",
        "<NO_DIRECTION>": "unknown",
        "<NO_DIRECTIVE please>": "unknown",
        "notes: <NO_DIRECTIVE>": "unknown",
        "prefix <NO_DIRECTIPLE>": "unknown",
        "<NOT_DIRECTIVE>": "unknown",
        "<NO_DIRECTIPLE>": "unknown",
        "<NO_DIRECTIVE>": "no_directive",
    }
    for raw, expected_cls in cases.items():
        validated = validate_preprocessor_output(raw)
        assert validated["classification"] == expected_cls
        assert validated["output"] is None


def test_parse_rejects_near_miss_directives_when_wrapped_or_prefixed() -> None:
    cases = [
        "`set premise to concise replies`",
        '"use podman not docker"',
        "example: clear state",
        "notes: [set premise to concise replies]",
        'he said "use docker"',
    ]
    for raw in cases:
        assert parse_preprocessor_output(raw) is None


@given(st.one_of(st.none(), st.integers(), st.text(max_size=120)))
def test_parse_output_idempotent(raw_output: object) -> None:
    first = parse_preprocessor_output(raw_output)
    second = parse_preprocessor_output(first)
    if first is None:
        assert second is None
    else:
        assert second == first


@given(
    st.one_of(
        st.none(), st.integers(), st.text(max_size=120), st.dictionaries(st.text(), st.none())
    )
)
def test_validate_output_always_has_null_for_non_directive(raw_output: object) -> None:
    validated = validate_preprocessor_output(raw_output)
    if validated["classification"] == "directive":
        assert isinstance(validated["output"], str)
    else:
        assert validated["output"] is None
