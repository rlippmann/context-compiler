import pytest

from context_compiler import create_engine


def test_clear_state_then_correction_requires_clarification() -> None:
    engine = create_engine()
    engine.step("use Nord Stage 4")
    engine.step("clear state")

    decision = engine.step("actually Nord Stage 3")

    assert decision["kind"] == "clarify"
    assert engine.state == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": []},
        "version": 1,
    }


def test_pending_blocks_reset_policies_until_yes_no_resolution() -> None:
    engine = create_engine()
    first = engine.step("no use docker")
    assert first["kind"] == "clarify"

    decision = engine.step("reset policies")

    assert decision["kind"] == "clarify"
    assert (
        decision["prompt_to_user"] == "Did you mean to prohibit 'docker'? Please answer yes or no."
    )
    assert engine.state == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": []},
        "version": 1,
    }


def test_pending_blocks_clear_state_until_yes_no_resolution() -> None:
    engine = create_engine()
    first = engine.step("no use docker")
    assert first["kind"] == "clarify"

    decision = engine.step("clear state")

    assert decision["kind"] == "clarify"
    assert (
        decision["prompt_to_user"] == "Did you mean to prohibit 'docker'? Please answer yes or no."
    )
    assert engine.state == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": []},
        "version": 1,
    }


def test_pending_blocks_allow_until_yes_no_resolution() -> None:
    engine = create_engine()
    first = engine.step("no use docker")
    assert first["kind"] == "clarify"

    decision = engine.step("allow docker")

    assert decision["kind"] == "clarify"
    assert (
        decision["prompt_to_user"] == "Did you mean to prohibit 'docker'? Please answer yes or no."
    )
    assert engine.state == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": []},
        "version": 1,
    }


def test_policy_then_fact_then_correction_targets_fact_not_policy() -> None:
    engine = create_engine()
    engine.step("don't use docker")
    engine.step("use Nord Stage 4")

    decision = engine.step("actually Nord Stage 3")

    assert decision["kind"] == "update"
    assert engine.state == {
        "facts": {"focus.primary": "Nord Stage 3"},
        "policies": {"prohibit": ["docker"]},
        "version": 1,
    }


def test_i_meant_marker_behaves_like_actually() -> None:
    engine = create_engine()
    engine.step("use Nord Stage 4")

    decision = engine.step("I meant Nord Stage 3")

    assert decision["kind"] == "update"
    assert engine.state == {
        "facts": {"focus.primary": "Nord Stage 3"},
        "policies": {"prohibit": []},
        "version": 1,
    }


def test_no_comma_marker_behaves_like_actually_when_fact_exists() -> None:
    engine = create_engine()
    engine.step("use Nord Stage 4")

    decision = engine.step("no, Nord Stage 3")

    assert decision["kind"] == "update"
    assert engine.state == {
        "facts": {"focus.primary": "Nord Stage 3"},
        "policies": {"prohibit": []},
        "version": 1,
    }


def test_mixed_positive_and_negative_in_one_utterance_requires_clarify() -> None:
    engine = create_engine()
    engine.step("use baseline")
    before = engine.state

    decision = engine.step("use Nord Stage 4 and don't use docker")

    assert decision["kind"] == "clarify"
    assert engine.state == before


def test_mixed_negative_and_allow_in_one_utterance_requires_clarify() -> None:
    engine = create_engine()
    engine.step("use baseline")
    before = engine.state

    decision = engine.step("don't use docker and allow shellfish")

    assert decision["kind"] == "clarify"
    assert engine.state == before


def test_mixed_allow_and_negative_in_one_utterance_requires_clarify() -> None:
    engine = create_engine()
    engine.step("don't use shellfish")
    before = engine.state

    decision = engine.step("allow docker and don't use shellfish")

    assert decision["kind"] == "clarify"
    assert engine.state == before


@pytest.mark.parametrize(
    "response",
    [
        "yes",
        "YES",
        "yes.",
        "yes!",
        "yes!!!",
        "yes please",
        "Yes please.",
        "  yes   please  ",
        "yep",
        "yeah!",
        "sure",
        "SURE!",
        "ok",
        "OK.",
        "okay",
        "Okay!",
    ],
)
def test_pending_confirmation_accepts_affirmative_variants(response: str) -> None:
    engine = create_engine()
    engine.step("no use docker")

    decision = engine.step(response)

    assert decision["kind"] == "update"
    assert engine.state == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": ["docker"]},
        "version": 1,
    }


@pytest.mark.parametrize(
    "response",
    [
        "no",
        "NO",
        "no.",
        "no!",
        "no!!",
        "no!!!",
        "no!!!!!",
        "nope",
        "no thanks",
        "no thanks!",
        "  no   thanks!  ",
    ],
)
def test_pending_confirmation_accepts_negative_variants(response: str) -> None:
    engine = create_engine()
    before = engine.state
    engine.step("no use docker")

    decision = engine.step(response)

    assert decision["kind"] == "passthrough"
    assert engine.state == before


@pytest.mark.parametrize(
    "response",
    [
        "yes maybe",
        "yeah maybe",
        "sure maybe",
        "ok maybe",
        "no maybe",
        "maybe",
        "sounds good",
        "works for me",
        "y",
        "n",
    ],
)
def test_pending_confirmation_rejects_non_matching_phrases(response: str) -> None:
    engine = create_engine()
    engine.step("no use docker")

    decision = engine.step(response)

    assert decision["kind"] == "clarify"
    assert (
        decision["prompt_to_user"] == "Did you mean to prohibit 'docker'? Please answer yes or no."
    )
    assert engine.state == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": []},
        "version": 1,
    }


def test_correction_payload_that_looks_like_command_requires_clarify() -> None:
    engine = create_engine()
    engine.step("use Nord Stage 4")
    before = engine.state

    decision = engine.step("actually don't use docker")

    assert decision["kind"] == "clarify"
    assert engine.state == before
