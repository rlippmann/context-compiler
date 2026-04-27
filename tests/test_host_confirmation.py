from hypothesis import assume, given
from hypothesis import strategies as st

import host_support.confirmation as _confirmation

_EXPECTED_CONFIRMATION_TOKENS = frozenset(
    {
        "yes",
        "yes please",
        "yep",
        "yeah",
        "sure",
        "ok",
        "okay",
        "no",
        "nope",
        "no thanks",
    }
)

_TRAILING_PUNCT = st.text(alphabet=".,!?", min_size=0, max_size=4)
_EDGE_WHITESPACE = st.text(alphabet=" \t\n\r", min_size=0, max_size=4)
_INTERNAL_WHITESPACE = st.text(alphabet=" \t\n\r", min_size=1, max_size=4)


def _apply_mixed_case(value: str, flags: list[bool]) -> str:
    if not flags:
        return value
    chars: list[str] = []
    for index, char in enumerate(value):
        flag = flags[index % len(flags)]
        chars.append(char.upper() if flag else char.lower())
    return "".join(chars)


def test_confirmation_tokens_match_spec_exactly() -> None:
    assert _confirmation.CONFIRMATION_TOKENS == _EXPECTED_CONFIRMATION_TOKENS


def test_normalize_confirmation_text_examples() -> None:
    assert _confirmation.normalize_confirmation_text(" YES!  ") == "yes"
    assert _confirmation.normalize_confirmation_text("yes   please.") == "yes please"
    assert _confirmation.normalize_confirmation_text("no thanks.") == "no thanks"
    assert _confirmation.normalize_confirmation_text("Okay??") == "okay"


def test_is_confirmation_text_accepts_spec_tokens() -> None:
    for token in sorted(_EXPECTED_CONFIRMATION_TOKENS):
        assert _confirmation.is_confirmation_text(token)


def test_is_confirmation_text_rejects_required_near_misses() -> None:
    rejected = [
        "y",
        "n",
        "yes but explain",
        "okay now answer",
        "sure, explain",
        "",
        "   \t\n  ",
    ]
    for value in rejected:
        assert not _confirmation.is_confirmation_text(value)


@given(
    token=st.sampled_from(sorted(_EXPECTED_CONFIRMATION_TOKENS)),
    leading_ws=_EDGE_WHITESPACE,
    trailing_ws=_EDGE_WHITESPACE,
    internal_ws=_INTERNAL_WHITESPACE,
    trailing_punct=_TRAILING_PUNCT,
    case_flags=st.lists(st.booleans(), min_size=1, max_size=8),
)
def test_accepted_tokens_survive_normalization_variants(
    token: str,
    leading_ws: str,
    trailing_ws: str,
    internal_ws: str,
    trailing_punct: str,
    case_flags: list[bool],
) -> None:
    spaced = token.replace(" ", internal_ws)
    cased = _apply_mixed_case(spaced, case_flags)
    candidate = f"{leading_ws}{cased}{trailing_punct}{trailing_ws}"
    assert _confirmation.is_confirmation_text(candidate)


@given(
    token=st.sampled_from(sorted(_EXPECTED_CONFIRMATION_TOKENS)),
    extra_text=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ",
        min_size=1,
        max_size=20,
    ),
)
def test_semantic_extensions_after_valid_token_are_rejected(token: str, extra_text: str) -> None:
    normalized_extra = _confirmation.normalize_confirmation_text(extra_text)
    assume(normalized_extra != "")
    candidate = f"{token} {extra_text}"
    assert not _confirmation.is_confirmation_text(candidate)


@given(
    st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?\t\n\r",
        min_size=0,
        max_size=40,
    )
)
def test_non_token_strings_are_rejected(value: str) -> None:
    normalized = _confirmation.normalize_confirmation_text(value)
    assume(normalized not in _confirmation.CONFIRMATION_TOKENS)
    assert not _confirmation.is_confirmation_text(value)
