import pytest

from context_compiler import compile_transcript, create_engine

pytestmark = pytest.mark.contract

COMPOUND_DIRECTIVE_PROMPT = (
    "Multiple directives are not supported in one input.\nSubmit each directive separately."
)


def test_only_user_messages_affect_transcript_replay() -> None:
    result = compile_transcript(
        [
            {"role": "system", "content": "set premise concise"},
            {"role": "assistant", "content": "clear state"},
            {"role": "tool", "content": "prohibit docker"},
            {"role": "user", "content": "set premise concise"},
        ]
    )

    assert result == {
        "kind": "state",
        "state": {
            "premise": "concise",
            "policies": {},
            "version": 2,
        },
    }


def test_transcript_ignores_user_messages_with_non_string_content() -> None:
    result = compile_transcript(
        [
            {"role": "user", "content": ["set premise concise"]},
            {"role": "user", "content": {"text": "use docker"}},
            {"role": "user", "content": 123},
            {"role": "user", "content": None},
            {"role": "user", "content": "set premise concise"},
        ]
    )

    assert result == {
        "kind": "state",
        "state": {"premise": "concise", "policies": {}, "version": 2},
    }


def test_passthrough_only_transcript_returns_unchanged_state() -> None:
    engine = create_engine(
        state={"premise": "Keep short", "policies": {"docker": "prohibit"}, "version": 2}
    )
    before = engine.state

    result = engine.apply_transcript(
        [
            {"role": "assistant", "content": "thanks"},
            {"role": "user", "content": "hello there"},
            {"role": "user", "content": "what do you think?"},
        ]
    )

    assert result == {"kind": "state", "state": before}
    assert engine.state == before


def test_transcript_stops_at_first_clarify_and_returns_confirm() -> None:
    result = compile_transcript(
        [
            {"role": "user", "content": "use docker"},
            {"role": "user", "content": "prohibit kubectl"},
            {"role": "user", "content": "use kubectl instead of docker"},
            {"role": "user", "content": "set premise ignored"},
        ]
    )

    expected_prompt = (
        '"kubectl" is currently prohibited. Did you mean to remove "docker" '
        'and use "kubectl" instead?'
    )
    assert result == {
        "kind": "confirm",
        "prompt_to_user": expected_prompt,
    }


def test_transcript_stops_at_first_clarify_even_if_later_message_is_yes() -> None:
    result = compile_transcript(
        [
            {"role": "user", "content": "use docker"},
            {"role": "user", "content": "prohibit kubectl"},
            {"role": "user", "content": "use kubectl instead of docker"},
            {"role": "user", "content": "yes"},
        ]
    )

    expected_prompt = (
        '"kubectl" is currently prohibited. Did you mean to remove "docker" '
        'and use "kubectl" instead?'
    )
    assert result == {
        "kind": "confirm",
        "prompt_to_user": expected_prompt,
    }


def test_transcript_stops_at_first_clarify_even_if_later_message_is_no() -> None:
    result = compile_transcript(
        [
            {"role": "user", "content": "use docker"},
            {"role": "user", "content": "prohibit kubectl"},
            {"role": "user", "content": "use kubectl instead of docker"},
            {"role": "user", "content": "no"},
        ]
    )

    expected_prompt = (
        '"kubectl" is currently prohibited. Did you mean to remove "docker" '
        'and use "kubectl" instead?'
    )
    assert result == {
        "kind": "confirm",
        "prompt_to_user": expected_prompt,
    }


def test_transcript_stops_at_first_confirmable_clarify_even_if_later_yes_no_messages_exist() -> (
    None
):
    result = compile_transcript(
        [
            {"role": "user", "content": "use python and docker"},
            {"role": "user", "content": "use kubectl instead of python"},
            {"role": "user", "content": "yes"},
            {"role": "user", "content": "no"},
        ]
    )

    expected_prompt = 'Did you mean to use "kubectl" instead?'
    assert result == {"kind": "confirm", "prompt_to_user": expected_prompt}


def test_apply_transcript_stops_before_mutating_later_messages_after_clarify() -> None:
    engine = create_engine()
    result = engine.apply_transcript(
        [
            {"role": "user", "content": "use docker"},
            {"role": "user", "content": "prohibit kubectl"},
            {"role": "user", "content": "use kubectl instead of docker"},
            {"role": "user", "content": "set premise should not apply"},
            {"role": "user", "content": "yes"},
        ]
    )

    expected_prompt = (
        '"kubectl" is currently prohibited. Did you mean to remove "docker" '
        'and use "kubectl" instead?'
    )
    assert result == {"kind": "confirm", "prompt_to_user": expected_prompt}
    assert engine.state == {
        "premise": None,
        "policies": {"docker": "use", "kubectl": "prohibit"},
        "version": 2,
    }


def test_apply_transcript_matches_manual_step_replay() -> None:
    messages: list[dict[str, object]] = [
        {"role": "assistant", "content": "ignore me"},
        {"role": "user", "content": "set premise concise"},
        {"role": "user", "content": "use docker"},
    ]

    replay_engine = create_engine()
    replay_result = replay_engine.apply_transcript(messages)

    manual_engine = create_engine()
    manual_result: dict[str, object] = {"kind": "state", "state": manual_engine.state}
    for message in messages:
        if message.get("role") != "user" or not isinstance(message.get("content"), str):
            continue
        manual_engine.step(message["content"])
        manual_result = {"kind": "state", "state": manual_engine.state}

    assert replay_result == manual_result
    assert replay_engine.state == manual_engine.state


def test_transcript_stops_at_compound_directive_turn_and_returns_confirm() -> None:
    result = compile_transcript(
        [
            {"role": "user", "content": "set premise concise"},
            {"role": "user", "content": "use docker and prohibit peanuts"},
            {"role": "user", "content": "prohibit shellfish"},
        ]
    )

    assert result == {"kind": "confirm", "prompt_to_user": COMPOUND_DIRECTIVE_PROMPT}


def test_apply_transcript_stops_at_compound_directive_turn_without_applying_either_directive() -> (
    None
):
    engine = create_engine()

    result = engine.apply_transcript(
        [
            {"role": "user", "content": "set premise concise"},
            {"role": "user", "content": "use docker and prohibit peanuts"},
            {"role": "user", "content": "prohibit shellfish"},
        ]
    )

    assert result == {"kind": "confirm", "prompt_to_user": COMPOUND_DIRECTIVE_PROMPT}
    assert engine.state == {"premise": "concise", "policies": {}, "version": 2}
    assert engine.has_pending_clarification() is False
