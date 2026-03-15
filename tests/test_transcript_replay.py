from context_compiler import compile_transcript, create_engine


def test_only_user_messages_affect_transcript_replay() -> None:
    result = compile_transcript(
        [
            {"role": "system", "content": "don't use docker"},
            {"role": "assistant", "content": "clear state"},
            {"role": "tool", "content": "use Nord Stage 4"},
            {"role": "user", "content": "don't use peanuts"},
        ]
    )

    assert result == {
        "kind": "state",
        "state": {
            "facts": {"focus.primary": None},
            "policies": {"prohibit": ["peanuts"]},
            "version": 1,
        },
    }


def test_passthrough_only_transcript_returns_unchanged_state() -> None:
    engine = create_engine()
    engine.step("don't use shellfish")
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


def test_transcript_with_updates_returns_final_state() -> None:
    result = compile_transcript(
        [
            {"role": "user", "content": "use Nord Stage 4"},
            {"role": "assistant", "content": "not a user turn"},
            {"role": "user", "content": "don't use peanuts and shellfish"},
            {"role": "user", "content": "allow shellfish"},
        ]
    )

    assert result == {
        "kind": "state",
        "state": {
            "facts": {"focus.primary": "Nord Stage 4"},
            "policies": {"prohibit": ["peanuts"]},
            "version": 1,
        },
    }


def test_transcript_with_clarify_returns_confirm_and_stops() -> None:
    engine = create_engine()

    result = engine.apply_transcript(
        [
            {"role": "user", "content": "don't use peanuts"},
            {"role": "user", "content": "no use shellfish"},
            {"role": "user", "content": "don't use gluten"},
        ]
    )

    assert result == {"kind": "confirm", "prompt_to_user": "Did you mean to prohibit 'shellfish'?"}
    assert engine.state == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": ["peanuts"]},
        "version": 1,
    }


def test_compile_transcript_is_deterministic_for_same_messages() -> None:
    messages: list[dict[str, object]] = [
        {"role": "user", "content": "use Nord Stage 4"},
        {"role": "user", "content": "don't use peanuts"},
        {"role": "user", "content": "allow peanuts"},
    ]

    assert compile_transcript(messages) == compile_transcript(messages)


def test_apply_transcript_matches_manual_step_replay() -> None:
    messages: list[dict[str, object]] = [
        {"role": "assistant", "content": "ignore me"},
        {"role": "user", "content": "don't use peanuts"},
        {"role": "user", "content": "no use shellfish"},
        {"role": "user", "content": "don't use gluten"},
    ]

    replay_engine = create_engine()
    replay_result = replay_engine.apply_transcript(messages)

    manual_engine = create_engine()
    manual_result: dict[str, object] = {"kind": "state", "state": manual_engine.state}
    for message in messages:
        if message.get("role") != "user" or not isinstance(message.get("content"), str):
            continue
        decision = manual_engine.step(message["content"])
        if decision["kind"] == "clarify":
            manual_result = {"kind": "confirm", "prompt_to_user": decision["prompt_to_user"]}
            break
        manual_result = {"kind": "state", "state": manual_engine.state}

    assert replay_result == manual_result
    assert replay_engine.state == manual_engine.state


def test_apply_transcript_respects_existing_pending_clarification_until_explicit_resolution() -> (
    None
):
    engine = create_engine()
    decision = engine.step("no use shellfish")
    assert decision == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": "Did you mean to prohibit 'shellfish'?",
    }

    blocked = engine.apply_transcript([{"role": "user", "content": "don't use gluten"}])
    assert blocked == {
        "kind": "confirm",
        "prompt_to_user": "Did you mean to prohibit 'shellfish'? Please answer yes or no.",
    }
    assert engine.state == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": []},
        "version": 1,
    }

    resolved = engine.apply_transcript(
        [
            {"role": "user", "content": "yes"},
            {"role": "user", "content": "don't use gluten"},
        ]
    )
    assert resolved == {
        "kind": "state",
        "state": {
            "facts": {"focus.primary": None},
            "policies": {"prohibit": ["gluten", "shellfish"]},
            "version": 1,
        },
    }


def test_apply_transcript_parity_after_import_json_state_replacement() -> None:
    source = create_engine()
    source.step("use Nord Stage 4")
    source.step("don't use peanuts")

    replaced = create_engine()
    replaced.import_json(source.export_json())

    transcript: list[dict[str, object]] = [
        {"role": "assistant", "content": "ignore"},
        {"role": "user", "content": "allow peanuts"},
        {"role": "user", "content": "don't use shellfish"},
    ]

    source_result = source.apply_transcript(transcript)
    replaced_result = replaced.apply_transcript(transcript)

    assert source_result == replaced_result
    assert source.state == replaced.state


def test_apply_transcript_stops_exactly_at_first_clarify_and_ignores_later_messages() -> None:
    engine = create_engine()

    result = engine.apply_transcript(
        [
            {"role": "user", "content": "don't use peanuts"},
            {"role": "user", "content": "no use shellfish"},
            {"role": "user", "content": "yes"},
            {"role": "user", "content": "don't use gluten"},
        ]
    )

    assert result == {"kind": "confirm", "prompt_to_user": "Did you mean to prohibit 'shellfish'?"}
    assert engine.state == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": ["peanuts"]},
        "version": 1,
    }

    decision_after = engine.step("yes")
    assert decision_after["kind"] == "update"
    assert engine.state == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": ["peanuts", "shellfish"]},
        "version": 1,
    }


def test_compile_transcript_public_api_import_and_smoke_use() -> None:
    from context_compiler import compile_transcript as public_compile_transcript

    result = public_compile_transcript([{"role": "user", "content": "don't use peanuts"}])
    assert result == {
        "kind": "state",
        "state": {
            "facts": {"focus.primary": None},
            "policies": {"prohibit": ["peanuts"]},
            "version": 1,
        },
    }


def test_compile_transcript_ignores_inserted_non_user_messages_metamorphic() -> None:
    baseline = [
        {"role": "user", "content": "use Nord Stage 4"},
        {"role": "user", "content": "don't use peanuts"},
        {"role": "user", "content": "allow peanuts"},
    ]
    noisy = [
        {"role": "system", "content": "you are helpful"},
        {"role": "user", "content": "use Nord Stage 4"},
        {"role": "assistant", "content": "ok"},
        {"role": "tool", "content": "don't use shellfish"},
        {"role": "user", "content": "don't use peanuts"},
        {"role": "assistant", "content": "noted"},
        {"role": "user", "content": "allow peanuts"},
    ]

    assert compile_transcript(noisy) == compile_transcript(baseline)


def test_apply_transcript_chunking_equivalence_when_no_clarify_interrupts() -> None:
    transcript: list[dict[str, object]] = [
        {"role": "user", "content": "use Nord Stage 4"},
        {"role": "user", "content": "don't use peanuts"},
        {"role": "assistant", "content": "ignore"},
        {"role": "user", "content": "allow peanuts"},
        {"role": "user", "content": "don't use shellfish"},
    ]

    one_shot = create_engine()
    one_shot_result = one_shot.apply_transcript(transcript)

    chunked = create_engine()
    first_half = chunked.apply_transcript(transcript[:2])
    second_half = chunked.apply_transcript(transcript[2:])

    assert first_half["kind"] == "state"
    assert second_half == one_shot_result
    assert chunked.state == one_shot.state
