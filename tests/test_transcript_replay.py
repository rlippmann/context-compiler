from context_compiler import compile_transcript, create_engine


def test_only_user_messages_affect_transcript_replay() -> None:
    result = compile_transcript(
        [
            {"role": "system", "content": "set premise concise"},
            {"role": "assistant", "content": "clear state"},
            {"role": "tool", "content": "don't use docker"},
            {"role": "user", "content": "hello"},
        ]
    )

    assert result == {
        "kind": "state",
        "state": {
            "premise": None,
            "policies": {},
            "version": 2,
        },
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


def test_compile_transcript_is_deterministic_for_same_messages() -> None:
    messages: list[dict[str, object]] = [
        {"role": "user", "content": "hello"},
        {"role": "user", "content": "world"},
    ]

    assert compile_transcript(messages) == compile_transcript(messages)


def test_apply_transcript_matches_manual_step_replay() -> None:
    messages: list[dict[str, object]] = [
        {"role": "assistant", "content": "ignore me"},
        {"role": "user", "content": "hello"},
        {"role": "user", "content": "world"},
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
