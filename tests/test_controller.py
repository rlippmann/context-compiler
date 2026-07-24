import json
from pathlib import Path

import pytest

from context_compiler import (
    create_engine,
    diff_has_changes,
    get_preview_decision,
    get_preview_state_after,
    get_step_decision,
    get_step_state,
    preview_would_mutate,
)
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


def test_preview_missing_source_replacement_reports_update_without_live_mutation() -> None:
    engine = create_engine()
    result = preview(engine, "use kubectl instead of docker")

    assert result["decision"] == {
        "kind": "update",
        "state": {"premise": None, "policies": {"kubectl": "use"}, "version": 2},
        "prompt_to_user": None,
    }
    assert result["state_before"] == {"premise": None, "policies": {}, "version": 2}
    assert result["state_after"] == {
        "premise": None,
        "policies": {"kubectl": "use"},
        "version": 2,
    }
    assert result["diff"]["changed"] is True
    assert result["would_mutate"] is True
    assert engine.has_pending_clarification() is False

    yes = engine.step("yes")
    assert yes["kind"] == "passthrough"


def test_preview_prohibited_replacement_clarify_matches_execution_without_pending() -> None:
    engine = create_engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")

    result = preview(engine, "use kubectl instead of docker")

    assert result["decision"] == {
        "kind": "clarify",
        "state": None,
        "prompt_to_user": (
            '"kubectl" is currently prohibited.\n'
            "Submit explicit directive(s) to remove it or use a different item."
        ),
    }
    assert result["state_before"] == result["state_after"] == engine.state
    assert result["would_mutate"] is False
    assert engine.has_pending_clarification() is False


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


@pytest.mark.contract
def test_state_diff_policy_removed_and_value_changed() -> None:
    before = {
        "premise": None,
        "policies": {"docker": "use", "pytest": "prohibit"},
        "version": 2,
    }
    after = {
        "premise": None,
        "policies": {"docker": "prohibit"},
        "version": 2,
    }

    diff = state_diff(before, after)
    assert diff["changed"] is True
    assert diff["premise"] == {"before": None, "after": None, "changed": False}
    assert diff["policies"]["removed"] == {"pytest": "prohibit"}
    assert diff["policies"]["changed"] == {"docker": {"before": "use", "after": "prohibit"}}
    assert diff["policies"]["added"] == {}


def test_preview_fails_when_state_restore_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine()

    def _boom(_: object) -> None:
        raise RuntimeError("restore failed")

    monkeypatch.setattr(engine, "import_json", _boom)
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


def test_controller_result_surface_contract_stability() -> None:
    engine = create_engine()

    step_result = step(engine, "set premise concise replies")
    assert set(step_result.keys()) == {"output_version", "mode", "decision", "state"}
    assert step_result["output_version"] == 1
    assert step_result["mode"] == "step"
    assert isinstance(step_result["state"], dict)

    preview_result = preview(engine, "use docker")
    assert set(preview_result.keys()) == {
        "output_version",
        "mode",
        "decision",
        "state_before",
        "state_after",
        "diff",
        "would_mutate",
    }
    assert preview_result["output_version"] == 1
    assert preview_result["mode"] == "preview"
    assert preview_result["would_mutate"] is preview_result["diff"]["changed"]


@pytest.mark.contract
def test_controller_helpers_match_public_result_keys() -> None:
    engine = create_engine()

    step_result = step(engine, "set premise concise replies")
    assert get_step_decision(step_result) is step_result["decision"]
    assert get_step_state(step_result) == step_result["state"]

    preview_result = preview(engine, "use docker")
    assert get_preview_decision(preview_result) is preview_result["decision"]
    assert get_preview_state_after(preview_result) == preview_result["state_after"]
    assert preview_would_mutate(preview_result) is preview_result["would_mutate"]

    diff = state_diff(preview_result["state_before"], preview_result["state_after"])
    assert diff_has_changes(diff) is diff["changed"]


def test_controller_helpers_are_importable_from_package_root() -> None:
    assert callable(get_step_decision)
    assert callable(get_step_state)
    assert callable(get_preview_decision)
    assert callable(get_preview_state_after)
    assert callable(preview_would_mutate)
    assert callable(diff_has_changes)


@pytest.mark.parametrize("confirmation", ["yes", "no"])
def test_preview_followup_tokens_after_invalid_replacement_are_passthrough(
    confirmation: str,
) -> None:
    engine = create_engine()
    initial = engine.step("use kubectl instead of docker")
    assert initial == {
        "kind": "update",
        "state": {"premise": None, "policies": {"kubectl": "use"}, "version": 2},
        "prompt_to_user": None,
    }
    assert engine.has_pending_clarification() is False

    preview_result = preview(engine, confirmation)
    assert preview_result["decision"] == {
        "kind": "passthrough",
        "state": None,
        "prompt_to_user": None,
    }
    assert preview_result["state_after"] == {
        "premise": None,
        "policies": {"kubectl": "use"},
        "version": 2,
    }
    assert preview_result["would_mutate"] is False

    assert engine.has_pending_clarification() is False
    assert engine.state == {"premise": None, "policies": {"kubectl": "use"}, "version": 2}

    final = step(engine, confirmation)
    assert final["decision"] == {"kind": "passthrough", "state": None, "prompt_to_user": None}
    assert final["state"] == {"premise": None, "policies": {"kubectl": "use"}, "version": 2}
    assert engine.has_pending_clarification() is False
