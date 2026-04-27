import importlib.util
import json
from pathlib import Path
from typing import Any, cast

import pytest

from context_compiler import create_engine


class _FakeEngine:
    def __init__(self, kind: str, checkpoint_out: str, *, has_pending: bool = False) -> None:
        self.kind = kind
        self.state: dict[str, object] = {"premise": None, "policies": {}, "version": 2}
        self._checkpoint_out = checkpoint_out
        self._has_pending = has_pending
        self.imported: list[str] = []
        self.step_calls = 0
        self.export_calls = 0

    def import_checkpoint_json(self, payload: str) -> None:
        self.imported.append(payload)

    def export_checkpoint_json(self) -> str:
        self.export_calls += 1
        return self._checkpoint_out

    def export_checkpoint(self) -> dict[str, object]:
        pending: object = None
        if self._has_pending:
            pending = {
                "kind": "replacement",
                "replacement": {"kind": "use_only", "new_item": "kubectl", "old_item": None},
                "prompt_to_user": "confirm?",
            }
        return {
            "checkpoint_version": 1,
            "authoritative_state": self.state,
            "pending": pending,
        }

    def step(self, _text: str) -> dict[str, object]:
        self.step_calls += 1
        if self.kind == "clarify":
            return {"kind": "clarify", "state": None, "prompt_to_user": "confirm?"}
        return {"kind": self.kind, "state": self.state}


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_checkpoint_behavior(module: object) -> None:
    checkpoints = cast(dict[str, str], module._CHECKPOINTS_BY_SESSION_KEY)
    restored = cast(dict[str, int], module._RESTORED_ENGINE_BY_SESSION_KEY)
    checkpoints.clear()
    restored.clear()

    call_litellm = cast(Any, module._call_litellm)
    module._call_litellm = lambda _messages: "ok"
    if hasattr(module, "_precompile_user_input"):
        module._precompile_user_input = lambda _text, _state: None

    try:
        checkpoints["s1"] = "ckpt-in"
        passthrough_engine = _FakeEngine("passthrough", "ckpt-passthrough")
        result = module.handle_turn("hello", passthrough_engine, session_key="s1")
        assert result == "ok"
        assert passthrough_engine.imported == ["ckpt-in"]
        assert passthrough_engine.export_calls == 0
        assert checkpoints["s1"] == "ckpt-in"

        update_engine = _FakeEngine("update", "ckpt-update")
        result = module.handle_turn("use docker", update_engine, session_key="s1")
        assert result == "ok"
        assert update_engine.imported == ["ckpt-in"]
        assert update_engine.export_calls == 1
        assert checkpoints["s1"] == "ckpt-update"

        clarify_engine = _FakeEngine("clarify", "ckpt-clarify")
        result = module.handle_turn(
            "use kubectl instead of docker", clarify_engine, session_key="s1"
        )
        assert result == "confirm?"
        assert clarify_engine.imported == ["ckpt-update"]
        assert clarify_engine.export_calls == 1
        assert checkpoints["s1"] == "ckpt-clarify"
    finally:
        module._call_litellm = call_litellm


def test_litellm_basic_checkpoint_restore_and_persist_points() -> None:
    module = _load_module(
        "litellm_basic_checkpoint", Path("examples/integrations/litellm/basic.py")
    )
    _assert_checkpoint_behavior(module)


def test_litellm_with_preprocessor_checkpoint_restore_and_persist_points() -> None:
    module = _load_module(
        "litellm_with_preprocessor_checkpoint",
        Path("examples/integrations/litellm/with_preprocessor.py"),
    )
    _assert_checkpoint_behavior(module)


@pytest.mark.parametrize(
    ("confirmation", "expected_response"),
    [
        ("yes", "State updated: Use kubectl."),
        ("no", "State unchanged."),
    ],
)
def test_litellm_with_preprocessor_bypasses_precompile_while_pending(
    confirmation: str, expected_response: str
) -> None:
    module = _load_module(
        "litellm_with_preprocessor_pending_bypass",
        Path("examples/integrations/litellm/with_preprocessor.py"),
    )

    class _PendingEngine:
        def __init__(self) -> None:
            self.state: dict[str, object] = {"premise": None, "policies": {}, "version": 2}
            self.pending = True
            self.step_inputs: list[str] = []

        def export_checkpoint(self) -> dict[str, object]:
            pending: object = None
            if self.pending:
                pending = {
                    "kind": "replacement",
                    "replacement": {"kind": "use_only", "new_item": "kubectl", "old_item": None},
                    "prompt_to_user": "confirm?",
                }
            return {
                "checkpoint_version": 1,
                "authoritative_state": self.state,
                "pending": pending,
            }

        def step(self, text: str) -> dict[str, object]:
            self.step_inputs.append(text)
            if self.pending and text in {"yes", "no"}:
                self.pending = False
                return {"kind": "update", "state": self.state}
            if self.pending:
                return {"kind": "clarify", "state": None, "prompt_to_user": "confirm?"}
            return {"kind": "passthrough", "state": None}

    call_litellm = cast(Any, module._call_litellm)
    precompile_user_input = cast(Any, module._precompile_user_input)

    def _fail_precompile(_text: str, _state: dict[str, object]) -> None:
        raise AssertionError("should not precompile")

    litellm_calls = 0

    def _track_litellm(_messages: list[dict[str, str]]) -> str:
        nonlocal litellm_calls
        litellm_calls += 1
        return "ok"

    module._call_litellm = _track_litellm
    module._precompile_user_input = _fail_precompile
    try:
        engine = _PendingEngine()
        result = module.handle_turn(confirmation, engine)
    finally:
        module._call_litellm = call_litellm
        module._precompile_user_input = precompile_user_input

    assert result == expected_response
    assert engine.step_inputs == [confirmation]
    assert litellm_calls == 0


@pytest.mark.parametrize(
    ("confirmation", "expected_policies", "expected_response"),
    [
        ("yes", {"kubectl": "use"}, "State updated: Use kubectl."),
        ("no", {}, "State unchanged."),
    ],
)
def test_litellm_with_preprocessor_checkpoint_resume_yes_no_end_to_end(
    confirmation: str, expected_policies: dict[str, str], expected_response: str
) -> None:
    module = _load_module(
        "litellm_with_preprocessor_checkpoint_resume_e2e",
        Path("examples/integrations/litellm/with_preprocessor.py"),
    )
    checkpoints = cast(dict[str, str], module._CHECKPOINTS_BY_SESSION_KEY)
    restored = cast(dict[str, int], module._RESTORED_ENGINE_BY_SESSION_KEY)
    checkpoints.clear()
    restored.clear()

    call_litellm = cast(Any, module._call_litellm)
    precompile_user_input = cast(Any, module._precompile_user_input)

    precompile_inputs: list[str] = []

    def _precompile_before_pending(text: str, _state: dict[str, object]) -> None:
        precompile_inputs.append(text)
        return None

    def _fail_precompile(_text: str, _state: dict[str, object]) -> None:
        raise AssertionError("precompile should be bypassed while pending is restored")

    litellm_calls = 0

    def _track_litellm(_messages: list[dict[str, str]]) -> str:
        nonlocal litellm_calls
        litellm_calls += 1
        return "ok"

    module._call_litellm = _track_litellm
    module._precompile_user_input = _precompile_before_pending
    session_key = "resume-e2e"

    try:
        first_engine = create_engine()
        clarify = module.handle_turn(
            "use kubectl instead of docker",
            first_engine,
            session_key=session_key,
        )
        assert clarify == 'Did you mean to use "kubectl" instead?'
        assert precompile_inputs == ["use kubectl instead of docker"]
        assert session_key in checkpoints

        module._precompile_user_input = _fail_precompile
        second_engine = create_engine()
        resumed = module.handle_turn(confirmation, second_engine, session_key=session_key)
        assert resumed == expected_response
        assert second_engine.state == {
            "premise": None,
            "policies": expected_policies,
            "version": 2,
        }
        resumed_checkpoint = json.loads(checkpoints[session_key])
        assert resumed_checkpoint["pending"] is None
        assert litellm_calls == 0
    finally:
        module._call_litellm = call_litellm
        module._precompile_user_input = precompile_user_input


@pytest.mark.parametrize(
    ("confirmation", "expected_policies", "expected_response"),
    [
        ("yes", {"docker": "use"}, "State updated: Use docker."),
        ("YES!", {"docker": "use"}, "State updated: Use docker."),
        (" yes please ", {"docker": "use"}, "State updated: Use docker."),
        ("no thanks.", {}, "State unchanged."),
    ],
)
def test_litellm_basic_confirmation_update_returns_ack_without_downstream_model_call(
    confirmation: str, expected_policies: dict[str, str], expected_response: str
) -> None:
    module = _load_module(
        "litellm_basic_confirmation_ack",
        Path("examples/integrations/litellm/basic.py"),
    )
    checkpoints = cast(dict[str, str], module._CHECKPOINTS_BY_SESSION_KEY)
    restored = cast(dict[str, int], module._RESTORED_ENGINE_BY_SESSION_KEY)
    checkpoints.clear()
    restored.clear()

    call_litellm = cast(Any, module._call_litellm)
    litellm_calls = 0

    def _track_litellm(_messages: list[dict[str, str]]) -> str:
        nonlocal litellm_calls
        litellm_calls += 1
        raise AssertionError("downstream model should not be called")

    module._call_litellm = _track_litellm
    session_key = "basic-confirmation-ack"

    try:
        first_engine = create_engine()
        clarify = module.handle_turn(
            "use docker instead of kubectl",
            first_engine,
            session_key=session_key,
        )
        assert clarify == 'Did you mean to use "docker" instead?'
        assert session_key in checkpoints
        first_checkpoint = json.loads(checkpoints[session_key])
        assert first_checkpoint["pending"] is not None

        second_engine = create_engine()
        resumed = module.handle_turn(confirmation, second_engine, session_key=session_key)
        assert resumed == expected_response
        assert litellm_calls == 0
        assert second_engine.state == {
            "premise": None,
            "policies": expected_policies,
            "version": 2,
        }
        resumed_checkpoint = json.loads(checkpoints[session_key])
        assert resumed_checkpoint["pending"] is None
    finally:
        module._call_litellm = call_litellm


def test_litellm_basic_confirmation_summary_true_replacement() -> None:
    module = _load_module(
        "litellm_basic_confirmation_replace_summary",
        Path("examples/integrations/litellm/basic.py"),
    )
    checkpoints = cast(dict[str, str], module._CHECKPOINTS_BY_SESSION_KEY)
    restored = cast(dict[str, int], module._RESTORED_ENGINE_BY_SESSION_KEY)
    checkpoints.clear()
    restored.clear()

    call_litellm = cast(Any, module._call_litellm)
    module._call_litellm = lambda _messages: "ok"
    session_key = "basic-replace-summary"

    try:
        engine = create_engine()
        assert module.handle_turn("use podman", engine, session_key=session_key) == "ok"
        assert module.handle_turn("prohibit docker", engine, session_key=session_key) == "ok"
        clarify = module.handle_turn(
            "use docker instead of podman", engine, session_key=session_key
        )
        assert (
            clarify == '"docker" is currently prohibited. '
            'Did you mean to remove "podman" and use "docker" instead?'
        )

        resumed = module.handle_turn("yes", create_engine(), session_key=session_key)
        assert resumed == "State updated: Replaced podman with docker."
    finally:
        module._call_litellm = call_litellm


def test_litellm_basic_confirmation_summary_prohibited_old_replacement() -> None:
    module = _load_module(
        "litellm_basic_confirmation_prohibited_old_summary",
        Path("examples/integrations/litellm/basic.py"),
    )
    checkpoints = cast(dict[str, str], module._CHECKPOINTS_BY_SESSION_KEY)
    restored = cast(dict[str, int], module._RESTORED_ENGINE_BY_SESSION_KEY)
    checkpoints.clear()
    restored.clear()

    call_litellm = cast(Any, module._call_litellm)
    module._call_litellm = lambda _messages: "ok"
    session_key = "basic-prohibited-old-summary"

    try:
        engine = create_engine()
        assert module.handle_turn("prohibit docker", engine, session_key=session_key) == "ok"
        clarify = module.handle_turn(
            "use podman instead of docker", engine, session_key=session_key
        )
        assert (
            clarify == '"docker" is currently prohibited. '
            'Did you mean to remove it and use "podman" instead?'
        )

        resumed = module.handle_turn("yes", create_engine(), session_key=session_key)
        assert resumed == "State updated: Removed prohibition on docker; use podman."
    finally:
        module._call_litellm = call_litellm


def test_litellm_basic_confirmation_summary_falls_back_for_unknown_pending_shape() -> None:
    module = _load_module(
        "litellm_basic_confirmation_summary_fallback",
        Path("examples/integrations/litellm/basic.py"),
    )

    class _FallbackPendingEngine:
        def __init__(self) -> None:
            self.state: dict[str, object] = {"premise": None, "policies": {}, "version": 2}
            self._pending = {
                "kind": "replacement",
                "replacement": {
                    "kind": "unknown_kind",
                    "new_item": "docker",
                    "old_item": "podman",
                },
                "prompt_to_user": "confirm?",
            }

        def export_checkpoint(self) -> dict[str, object]:
            return {
                "checkpoint_version": 1,
                "authoritative_state": self.state,
                "pending": self._pending,
            }

        def export_checkpoint_json(self) -> str:
            return "ckpt-fallback"

        def step(self, _text: str) -> dict[str, object]:
            self._pending = None
            return {"kind": "update", "state": self.state}

    checkpoints = cast(dict[str, str], module._CHECKPOINTS_BY_SESSION_KEY)
    restored = cast(dict[str, int], module._RESTORED_ENGINE_BY_SESSION_KEY)
    checkpoints.clear()
    restored.clear()

    call_litellm = cast(Any, module._call_litellm)
    litellm_calls = 0

    def _track_litellm(_messages: list[dict[str, str]]) -> str:
        nonlocal litellm_calls
        litellm_calls += 1
        return "ok"

    module._call_litellm = _track_litellm
    try:
        result = module.handle_turn(
            "yes",
            _FallbackPendingEngine(),
            session_key="basic-summary-fallback",
        )
    finally:
        module._call_litellm = call_litellm

    assert result == "State updated."
    assert litellm_calls == 0
    assert checkpoints["basic-summary-fallback"] == "ckpt-fallback"
