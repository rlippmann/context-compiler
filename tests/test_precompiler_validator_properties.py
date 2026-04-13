import string

from hypothesis import assume, given
from hypothesis import strategies as st

from experimental.preprocessor.constants import PRECOMPILER_NO_DIRECTIVE_SENTINEL
from experimental.preprocessor.output_validation import (
    _is_allowed_directive,
    _normalize_precompiler_output,
    parse_precompiler_output,
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

MALFORMED_ABSTAIN = st.one_of(
    st.sampled_from(
        [
            "<NO_DIRECTIPLE>",
            "<NO_DIRECTITIVE>",
            "<NO_DIRECT_DIRECTIVE>",
            "<NO_DIRECTDirective> Directive cannot be generated...",
        ]
    ),
    st.builds(
        lambda middle: f"<NO_DIRECT{middle}>",
        st.text(alphabet=string.ascii_uppercase + "_", min_size=1, max_size=20),
    ),
    st.builds(
        lambda middle, suffix: f"<NO_DIRECT{middle}> {suffix}",
        st.text(alphabet=string.ascii_uppercase + "_", min_size=1, max_size=20),
        st.text(min_size=1, max_size=40),
    ),
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
    assert parse_precompiler_output(raw_output) is None


@given(NOISY_TEXT)
def test_parse_invalid_text_never_becomes_directive(text: str) -> None:
    stripped = text.strip()
    assume(stripped.upper() != PRECOMPILER_NO_DIRECTIVE_SENTINEL)
    assume(not _is_allowed_directive(stripped))
    parsed = parse_precompiler_output(text)
    assert parsed in {None, PRECOMPILER_NO_DIRECTIVE_SENTINEL}


@given(MALFORMED_ABSTAIN)
def test_parse_malformed_abstain_only_maps_to_sentinel_or_rejects(text: str) -> None:
    parsed = parse_precompiler_output(text)
    assert parsed in {None, PRECOMPILER_NO_DIRECTIVE_SENTINEL}


@given(st.sampled_from(CANONICAL_DIRECTIVES), SPACE_TEXT, SPACE_TEXT)
def test_parse_valid_canonical_directive_always_passes(
    directive: str, leading_ws: str, trailing_ws: str
) -> None:
    raw = f"{leading_ws}{directive}{trailing_ws}"
    assert parse_precompiler_output(raw) == directive


@given(NOISY_TEXT)
def test_normalization_is_idempotent(text: str) -> None:
    normalized_once = _normalize_precompiler_output(text)
    if normalized_once is None:
        return
    assert _normalize_precompiler_output(normalized_once) == normalized_once


@given(st.sampled_from(CANONICAL_DIRECTIVES), NON_EMPTY_TEXT, NON_EMPTY_TEXT)
def test_parse_rejects_directive_with_surrounding_text(
    directive: str, prefix: str, suffix: str
) -> None:
    raw = f"{prefix} {directive} {suffix}"
    stripped = raw.strip()
    assume(stripped.upper() != PRECOMPILER_NO_DIRECTIVE_SENTINEL)
    assume(not _is_allowed_directive(stripped))
    parsed = parse_precompiler_output(raw)
    assert parsed in {None, PRECOMPILER_NO_DIRECTIVE_SENTINEL}


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
    assert parse_precompiler_output(wrapped) is None


def test_parse_malformed_abstain_negative_boundaries_remain_narrow() -> None:
    cases = {
        "<NO_DIRECT>": None,
        "<NO_DIRECTION>": None,
        "<NO_DIRECTIVE please>": None,
        "notes: <NO_DIRECTIVE>": None,
        "prefix <NO_DIRECTIPLE>": None,
        "<NOT_DIRECTIVE>": None,
        "<NO_DIRECTIPLE>": PRECOMPILER_NO_DIRECTIVE_SENTINEL,
    }
    for raw, expected in cases.items():
        parsed = parse_precompiler_output(raw)
        assert parsed == expected
        if parsed is not None:
            assert parsed == PRECOMPILER_NO_DIRECTIVE_SENTINEL or _is_allowed_directive(parsed)


def test_parse_rejects_near_miss_directives_when_wrapped_or_prefixed() -> None:
    cases = [
        "`set premise to concise replies`",
        '"use podman not docker"',
        "example: clear state",
        "notes: [set premise to concise replies]",
        'he said "use docker"',
    ]
    for raw in cases:
        parsed = parse_precompiler_output(raw)
        assert parsed in {None, PRECOMPILER_NO_DIRECTIVE_SENTINEL}
        if parsed is not None:
            assert parsed == PRECOMPILER_NO_DIRECTIVE_SENTINEL


@given(st.one_of(st.none(), st.integers(), st.text(max_size=120)))
def test_parse_output_idempotent(raw_output: object) -> None:
    first = parse_precompiler_output(raw_output)
    second = parse_precompiler_output(first)
    if first is None:
        assert second is None
    else:
        assert second == first
