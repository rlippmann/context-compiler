import importlib.util
from pathlib import Path
from typing import Any, cast


class _FakeEngine:
    def __init__(self, kind: str, checkpoint_out: str) -> None:
        self.kind = kind
        self.state: dict[str, object] = {"premise": None, "policies": {}, "version": 2}
        self._checkpoint_out = checkpoint_out
        self.imported: list[str] = []
        self.step_calls = 0
        self.export_calls = 0

    def import_checkpoint_json(self, payload: str) -> None:
        self.imported.append(payload)

    def export_checkpoint_json(self) -> str:
        self.export_calls += 1
        return self._checkpoint_out

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
