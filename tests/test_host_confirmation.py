from typing import Any

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

import host_support.confirmation as _confirmation
from context_compiler import create_engine

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


def test_is_confirmation_text_normalization_examples() -> None:
    assert _confirmation.is_confirmation_text(" YES!  ")
    assert _confirmation.is_confirmation_text("yes   please.")
    assert _confirmation.is_confirmation_text("no thanks.")
    assert _confirmation.is_confirmation_text("Okay??")


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


def test_summarize_confirmation_update_use_only_summary_with_label_normalization() -> None:
    pending = {
        "replacement": {"kind": "use_only", "new_item": "  Docker   Compose  ", "old_item": None}
    }
    result = _confirmation.summarize_confirmation_update("yes", pending)
    assert result == "State updated: Use Docker Compose."


def test_summarize_confirmation_update_replace_use_summary() -> None:
    pending = {
        "replacement": {"kind": "replace_use", "new_item": "podman", "old_item": "docker"},
        "prompt_to_user": 'Did you mean to replace "docker" with "podman"?',
    }
    result = _confirmation.summarize_confirmation_update("yes", pending)
    assert result == "State updated: Replaced docker with podman."


def test_summarize_confirmation_update_replace_use_prohibited_old_prompt_summary() -> None:
    pending = {
        "replacement": {"kind": "replace_use", "new_item": "podman", "old_item": "docker"},
        "prompt_to_user": (
            '"docker" is currently prohibited. Did you mean to remove it and use "podman" instead?'
        ),
    }
    result = _confirmation.summarize_confirmation_update("yes", pending)
    assert result == "State updated: Removed prohibition on docker; use podman."


def test_summarize_confirmation_update_declined_returns_state_unchanged() -> None:
    pending = {
        "replacement": {"kind": "use_only", "new_item": "docker", "old_item": None},
    }
    result = _confirmation.summarize_confirmation_update("no thanks.", pending)
    assert result == "State unchanged."


def test_summarize_confirmation_update_unexpected_shape_falls_back_safely() -> None:
    pending = {"replacement": {"kind": "replace_use", "new_item": None, "old_item": "docker"}}
    result = _confirmation.summarize_confirmation_update("yes", pending)
    assert result == "State updated."


def test_summarize_confirmation_update_affirmative_pending_not_dict_falls_back() -> None:
    result = _confirmation.summarize_confirmation_update("yes", ["not-a-dict"])
    assert "State updated." in result


def test_summarize_confirmation_update_replacement_not_dict_falls_back() -> None:
    pending = {"replacement": "not-a-dict"}
    result = _confirmation.summarize_confirmation_update("yes", pending)
    assert "State updated." in result


def test_summarize_confirmation_update_unrecognized_replacement_shape_falls_back() -> None:
    pending = {"replacement": {"kind": "unknown_kind", "new_item": "docker", "old_item": None}}
    result = _confirmation.summarize_confirmation_update("yes", pending)
    assert "State updated." in result


def test_summarize_confirmation_update_use_only_empty_new_item_falls_back() -> None:
    pending = {"replacement": {"kind": "use_only", "new_item": "   ", "old_item": None}}
    result = _confirmation.summarize_confirmation_update("yes", pending)
    assert "State updated." in result


@pytest.mark.parametrize(
    ("new_item", "old_item"),
    [
        ("   ", "docker"),
        ("podman", "   "),
    ],
)
def test_summarize_confirmation_update_replace_use_empty_items_falls_back(
    new_item: str, old_item: str
) -> None:
    pending = {"replacement": {"kind": "replace_use", "new_item": new_item, "old_item": old_item}}
    result = _confirmation.summarize_confirmation_update("yes", pending)
    assert "State updated." in result


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
    assume(extra_text.strip() != "")
    candidate = f"{token} {extra_text}"
    assert not _confirmation.is_confirmation_text(candidate)


@given(
    st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        min_size=1,
        max_size=40,
    )
)
def test_non_token_strings_are_rejected(value: str) -> None:
    assume(value.lower() not in _confirmation.CONFIRMATION_TOKENS)
    assert not _confirmation.is_confirmation_text(value)


def _create_engine_with_pending_confirmation() -> tuple[Any, dict[str, object], str]:
    engine = create_engine()
    pre_pending_state = engine.state
    first = engine.step("use docker instead of kubectl")
    assert first["kind"] == "clarify"
    pending_prompt = first["prompt_to_user"]
    assert isinstance(pending_prompt, str)
    checkpoint = engine.export_checkpoint()
    assert checkpoint["pending"] is not None
    return engine, pre_pending_state, pending_prompt


def test_engine_host_confirmation_parity_for_required_candidates() -> None:
    candidates = [
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
        "YES!",
        " yes please ",
        "no thanks.",
        "y",
        "n",
        "yes but explain",
        "okay now answer",
        "sure, explain",
        "",
        " \t\n ",
    ]

    for candidate in candidates:
        host_accepts = _confirmation.is_confirmation_text(candidate)
        engine, pre_pending_state, pending_prompt = _create_engine_with_pending_confirmation()

        decision = engine.step(candidate)
        checkpoint = engine.export_checkpoint()

        if host_accepts:
            assert decision["kind"] == "update"
            assert checkpoint["pending"] is None
        else:
            assert decision["kind"] == "clarify"
            assert decision["prompt_to_user"] == pending_prompt
            assert engine.state == pre_pending_state
            assert checkpoint["pending"] is not None


@given(
    st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?\t\n\r",
        min_size=0,
        max_size=40,
    )
)
def test_engine_host_confirmation_parity_property(value: str) -> None:
    host_accepts = _confirmation.is_confirmation_text(value)
    engine, pre_pending_state, pending_prompt = _create_engine_with_pending_confirmation()

    decision = engine.step(value)
    checkpoint = engine.export_checkpoint()
    engine_resolved = decision["kind"] == "update"

    assert engine_resolved == host_accepts
    if host_accepts:
        assert checkpoint["pending"] is None
    else:
        assert decision["prompt_to_user"] == pending_prompt
        assert engine.state == pre_pending_state
        assert checkpoint["pending"] is not None
