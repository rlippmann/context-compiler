import json
from pathlib import Path

import pytest

from context_compiler import compile_transcript, create_engine
from context_compiler.controller import preview, state_diff, step

_STEP_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "conformance" / "step"
_TRANSCRIPT_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "transcript"
)
_STATE_JSON_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "state-json"
)
_CHECKPOINT_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "checkpoint"
)
_CONTROLLER_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "controller"
)


def _json_files(dir_path: Path) -> list[Path]:
    return sorted(dir_path.glob("*.json"))


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_optional_pending_flag(expected_obj: object, engine: object, fixture_id: object) -> None:
    if not isinstance(expected_obj, dict):
        return
    if "has_pending_clarification" not in expected_obj:
        return

    expected_pending = expected_obj["has_pending_clarification"]
    assert isinstance(expected_pending, bool), fixture_id
    assert engine.has_pending_clarification() is expected_pending, fixture_id


def test_step_fixtures() -> None:
    for path in _json_files(_STEP_FIXTURES_DIR):
        fixture = _load(path)
        fixture_id = fixture["id"]

        assert fixture["kind"] == "step", fixture_id

        engine = create_engine(state=fixture["initial_state"])
        prelude = fixture.get("prelude", [])
        for prior_input in prelude:
            engine.step(prior_input)
        decision = engine.step(fixture["input"])

        expected = fixture["expected"]
        expected_decision = expected["decision"]

        assert decision["kind"] == expected_decision["kind"], fixture_id

        if decision["kind"] == "clarify":
            assert decision["state"] == expected_decision["state"], fixture_id
            expected_prompt = expected_decision["prompt_to_user"]
            actual_prompt = decision["prompt_to_user"]
            if expected_prompt is None:
                assert isinstance(actual_prompt, str) and actual_prompt != "", fixture_id
            else:
                assert actual_prompt == expected_prompt, fixture_id
        else:
            assert decision == expected_decision, fixture_id

        if decision["kind"] == "update":
            assert decision["state"] == engine.state, fixture_id

        assert engine.state == expected["state"], fixture_id
        _assert_optional_pending_flag(expected, engine, fixture_id)


def test_transcript_fixtures() -> None:
    for path in _json_files(_TRANSCRIPT_FIXTURES_DIR):
        fixture = _load(path)
        fixture_id = fixture["id"]

        assert fixture["kind"] == "transcript", fixture_id

        result = compile_transcript(fixture["messages"])

        if (
            isinstance(result, dict)
            and set(result.keys()) == {"kind", "prompt_to_user"}
            and isinstance(result.get("prompt_to_user"), str)
        ):
            normalized = {
                "clarify": {
                    "prompt_to_user": result["prompt_to_user"],
                }
            }
        else:
            normalized = {"state": result}

        assert normalized == fixture["expected"], fixture_id


def _apply_prelude(engine: object, prelude: object) -> None:
    assert isinstance(prelude, list)
    for prior_input in prelude:
        assert isinstance(prior_input, str)
        engine.step(prior_input)


def test_state_json_fixtures() -> None:
    for path in _json_files(_STATE_JSON_FIXTURES_DIR):
        fixture = _load(path)
        fixture_id = fixture["id"]

        assert fixture["kind"] == "state_json", fixture_id
        engine = create_engine(state=fixture["initial_state"])
        _apply_prelude(engine, fixture.get("prelude", []))

        action = fixture["action"]
        expected = fixture["expected"]
        fn = action["fn"]

        if fn == "export_json":
            payload = engine.export_json()
            assert payload == expected["payload"], fixture_id
        elif fn == "import_json":
            payload = action["payload"]
            error = expected.get("error")
            if error is None:
                engine.import_json(payload)
            else:
                with pytest.raises(ValueError, match=error["message_contains"]):
                    engine.import_json(payload)
        else:
            raise AssertionError(f"Unknown state_json action: {fn}")

        assert engine.state == expected["state"], fixture_id


def test_checkpoint_fixtures() -> None:
    for path in _json_files(_CHECKPOINT_FIXTURES_DIR):
        fixture = _load(path)
        fixture_id = fixture["id"]

        assert fixture["kind"] == "checkpoint", fixture_id
        engine = create_engine(state=fixture["initial_state"])
        _apply_prelude(engine, fixture.get("prelude", []))

        action = fixture["action"]
        expected = fixture["expected"]
        fn = action["fn"]

        if fn == "import_checkpoint":
            payload = action["payload"]
            error = expected.get("error")
            if error is None:
                engine.import_checkpoint(payload)
            else:
                with pytest.raises(ValueError, match=error["message_contains"]):
                    engine.import_checkpoint(payload)
        elif fn == "export_checkpoint_json":
            payload = engine.export_checkpoint_json()
            if expected.get("payload_json_parseable"):
                parsed = json.loads(payload)
                assert parsed == expected["payload_object"], fixture_id
        elif fn == "import_checkpoint_json":
            payload = action["payload"]
            error = expected.get("error")
            if error is None:
                engine.import_checkpoint_json(payload)
            else:
                with pytest.raises(ValueError, match=error["message_contains"]):
                    engine.import_checkpoint_json(payload)
        elif fn == "checkpoint_json_round_trip":
            payload = engine.export_checkpoint_json()
            target = create_engine()
            target.import_checkpoint_json(payload)
            engine = target
        else:
            raise AssertionError(f"Unknown checkpoint action: {fn}")

        assert engine.state == expected["state"], fixture_id
        _assert_optional_pending_flag(expected, engine, fixture_id)

        followup = expected.get("followup")
        if followup is not None:
            decision = engine.step(followup["input"])
            assert decision == followup["decision"], fixture_id
            assert engine.state == followup["state"], fixture_id
            _assert_optional_pending_flag(followup, engine, fixture_id)


def test_controller_fixtures() -> None:
    for path in _json_files(_CONTROLLER_FIXTURES_DIR):
        fixture = _load(path)
        fixture_id = fixture["id"]

        assert fixture["kind"] == "controller", fixture_id
        engine = create_engine(state=fixture["initial_state"])
        _apply_prelude(engine, fixture.get("prelude", []))

        action = fixture["action"]
        expected = fixture["expected"]
        fn = action["fn"]

        if fn == "step":
            result = step(engine, action["input"])
            assert result == expected["result"], fixture_id
            assert engine.state == expected["state"], fixture_id
            _assert_optional_pending_flag(expected, engine, fixture_id)
            continue

        if fn == "preview":
            before = engine.state
            pending_before = engine.has_pending_clarification()
            result = preview(engine, action["input"])

            assert result == expected["result"], fixture_id
            assert engine.state == before, fixture_id
            assert engine.state == expected["state_after_preview"], fixture_id
            assert engine.has_pending_clarification() is pending_before, fixture_id
            _assert_optional_pending_flag(expected, engine, fixture_id)
            continue

        assert fn == "state_diff", fixture_id
        diff = state_diff(action["before"], action["after"])
        assert diff == expected["diff"], fixture_id
