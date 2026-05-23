import json
from pathlib import Path

import pytest

from context_compiler import create_engine
from context_compiler.controller import preview, state_diff, step

_CONTROLLER_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "controller"


def test_step_wrapper_returns_state_snapshot_and_contract_shape() -> None:
    engine = create_engine()
    result = step(engine, "set premise concise replies")

    assert result["output_version"] == 1
    assert result["mode"] == "step"
    assert result["decision"]["kind"] == "update"
    assert result["state"] == engine.state
    assert result["state"] == {
        "premise": "concise replies",
        "policies": {},
        "version": 2,
    }


def test_preview_update_does_not_mutate_engine_state() -> None:
    engine = create_engine()
    before = engine.state

    result = preview(engine, "set premise concise replies")

    assert result["mode"] == "preview"
    assert result["decision"]["kind"] == "update"
    assert result["state_before"] == before
    assert result["state_after"] == {
        "premise": "concise replies",
        "policies": {},
        "version": 2,
    }
    assert result["would_mutate"] is True
    assert result["would_mutate"] is result["diff"]["changed"]
    assert engine.state == before
    assert engine.has_pending_clarification() is False


def test_preview_clarify_path_and_pending_are_restored() -> None:
    engine = create_engine()
    result = preview(engine, "use kubectl instead of docker")

    assert result["decision"]["kind"] == "clarify"
    assert result["state_before"] == result["state_after"]
    assert result["diff"]["changed"] is False
    assert result["would_mutate"] is False
    assert engine.has_pending_clarification() is False

    yes = engine.step("yes")
    assert yes["kind"] == "passthrough"


def test_preview_pending_resolution_restores_existing_pending_state() -> None:
    engine = create_engine()
    first = engine.step("use kubectl instead of docker")
    assert first["kind"] == "clarify"
    assert engine.has_pending_clarification() is True

    result = preview(engine, "maybe")
    assert result["decision"]["kind"] == "clarify"
    assert result["would_mutate"] is False
    assert engine.has_pending_clarification() is True

    yes = engine.step("yes")
    assert yes["kind"] == "update"
    assert engine.state == {"premise": None, "policies": {"kubectl": "use"}, "version": 2}


def test_preview_idempotent_update_is_not_a_mutation() -> None:
    engine = create_engine()
    engine.step("use docker")
    before = engine.state

    result = preview(engine, "use docker")

    assert result["decision"]["kind"] == "update"
    assert result["state_before"] == result["state_after"]
    assert result["diff"]["changed"] is False
    assert result["would_mutate"] is False
    assert engine.state == before


def test_state_diff_structural_changes() -> None:
    before = {
        "premise": "concise",
        "policies": {"docker": "use", "pytest": "prohibit"},
        "version": 2,
    }
    after = {
        "premise": "formal",
        "policies": {"docker": "prohibit", "uv": "use"},
        "version": 2,
    }

    diff = state_diff(before, after)
    assert diff == {
        "changed": True,
        "premise": {
            "before": "concise",
            "after": "formal",
            "changed": True,
        },
        "policies": {
            "added": {"uv": "use"},
            "removed": {"pytest": "prohibit"},
            "changed": {"docker": {"before": "use", "after": "prohibit"}},
        },
    }


def test_preview_fails_when_checkpoint_restore_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine()

    def _boom(_: object) -> None:
        raise RuntimeError("restore failed")

    monkeypatch.setattr(engine, "import_checkpoint", _boom)
    with pytest.raises(RuntimeError, match="restore failed"):
        preview(engine, "set premise concise replies")


def test_controller_preview_fixtures() -> None:
    for path in sorted(_CONTROLLER_FIXTURES_DIR.glob("*.json")):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        fixture_id = fixture["id"]
        assert fixture["kind"] == "controller_preview", fixture_id

        engine = create_engine()
        for prior in fixture.get("prelude", []):
            engine.step(prior)
        before = engine.state
        result = preview(engine, fixture["input"])
        expected = fixture["expected"]

        assert result["decision"]["kind"] == expected["decision_kind"], fixture_id
        assert result["would_mutate"] is expected["would_mutate"], fixture_id
        assert result["diff"]["changed"] is expected["diff_changed"], fixture_id
        assert (result["state_before"] == result["state_after"]) is expected[
            "state_before_equals_after"
        ], fixture_id
        assert (engine.state == before) is expected["engine_state_unchanged_after_preview"], (
            fixture_id
        )
