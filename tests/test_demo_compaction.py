from demos.common import compact_user_turns


def test_compaction_drops_only_update_lines_and_keeps_passthrough_lines() -> None:
    compacted, state, prompt = compact_user_turns(
        ["hello", "set premise concise", "world", "use docker"]
    )

    assert compacted == ["hello", "world"]
    assert prompt is None
    assert state == {"premise": "concise", "policies": {"docker": "use"}, "version": 2}


def test_compaction_keeps_first_clarify_line_and_stops_replay() -> None:
    compacted, state, prompt = compact_user_turns(
        ["use docker", "prohibit docker", "set premise ignored", "hello"]
    )

    assert compacted == ["prohibit docker"]
    assert prompt == (
        "'docker' is already in use.\n"
        "Only one policy per item is allowed.\n"
        "Use 'reset policies' to change it."
    )
    assert state == {"premise": None, "policies": {"docker": "use"}, "version": 2}
