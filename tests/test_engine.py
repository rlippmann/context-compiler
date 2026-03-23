import json

import pytest

from context_compiler import compile_transcript, create_engine
from context_compiler.engine import DecisionKind, Engine


def test_decision_kind_strenum_behavior() -> None:
    for kind in DecisionKind:
        assert kind == kind.value
        assert str(kind) == kind.value
        assert DecisionKind(kind.value) is kind


def test_state_getter_returns_defensive_copy() -> None:
    engine = create_engine()
    snapshot = engine.state
    snapshot["premise"] = "mutated"
    snapshot["policies"]["docker"] = "use"

    assert engine.state == {"premise": None, "policies": {}, "version": 2}


def test_export_json_returns_complete_representation_of_state() -> None:
    engine = create_engine()
    payload = engine.export_json()
    assert json.loads(payload) == {"premise": None, "policies": {}, "version": 2}


def test_import_json_restores_state_exactly() -> None:
    engine = create_engine()
    expected = {
        "premise": "Use concise output",
        "policies": {"docker": "prohibit", "pytest": "use"},
        "version": 2,
    }

    engine.import_json(json.dumps(expected))

    assert engine.state == expected


def test_export_import_round_trip_preserves_state() -> None:
    source = create_engine(
        state={
            "premise": "Use concise output",
            "policies": {"docker": "prohibit", "pytest": "use"},
            "version": 2,
        }
    )

    target = create_engine()
    target.import_json(source.export_json())

    assert target.state == source.state


def test_import_json_invalid_json_and_unsupported_version_are_rejected() -> None:
    engine = create_engine()

    with pytest.raises(ValueError, match="Invalid JSON payload"):
        engine.import_json("{")

    with pytest.raises(ValueError, match="Unsupported state version"):
        engine.import_json(
            json.dumps(
                {
                    "premise": None,
                    "policies": {},
                    "version": 1,
                }
            )
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"premise": None, "version": 2},
        {"premise": [], "policies": {}, "version": 2},
        {"premise": None, "policies": [], "version": 2},
        {"premise": None, "policies": {"docker": "deny"}, "version": 2},
    ],
)
def test_import_json_rejects_structurally_invalid_payload(payload: dict[str, object]) -> None:
    engine = create_engine()
    with pytest.raises(ValueError):
        engine.import_json(json.dumps(payload))


def test_state_property_is_read_only() -> None:
    engine = create_engine()
    with pytest.raises(AttributeError):
        engine.state = {"premise": None, "policies": {}, "version": 2}


def test_step_passthrough_does_not_mutate_state() -> None:
    engine = create_engine()
    before = engine.state

    decision = engine.step("hello there")

    assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert engine.state == before


def test_compile_transcript_ignores_non_user_messages() -> None:
    result = compile_transcript(
        [
            {"role": "system", "content": "set premise concise"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "hello"},
        ]
    )

    assert result == {"kind": "state", "state": {"premise": None, "policies": {}, "version": 2}}


def test_apply_transcript_matches_manual_step_replay() -> None:
    messages: list[dict[str, object]] = [
        {"role": "assistant", "content": "ignore"},
        {"role": "user", "content": "hello"},
        {"role": "user", "content": "world"},
    ]

    replay_engine = create_engine()
    replay_result = replay_engine.apply_transcript(messages)

    manual_engine = create_engine()
    for message in messages:
        if message.get("role") == "user" and isinstance(message.get("content"), str):
            manual_engine.step(message["content"])

    assert replay_result == {"kind": "state", "state": manual_engine.state}
    assert replay_engine.state == manual_engine.state


def test_constructor_with_state_initializes_from_valid_state() -> None:
    state = {"premise": "Prefer bullets", "policies": {"pytest": "use"}, "version": 2}
    engine = Engine(state=state)
    assert engine.state == state
