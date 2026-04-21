import asyncio
import builtins
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

MODULE_PATH = Path("examples/integrations/openwebui/open_webui_pipe_with_preprocessor.py")


def _load_module_with_openwebui_stubs(
    module_name: str, monkeypatch, *, block_pydantic: bool = True
):
    fastapi_mod = types.ModuleType("fastapi")

    class _Request:  # minimal placeholder for type import
        pass

    fastapi_mod.Request = _Request

    open_webui_mod = types.ModuleType("open_webui")
    open_webui_models_mod = types.ModuleType("open_webui.models")
    open_webui_models_users_mod = types.ModuleType("open_webui.models.users")
    open_webui_utils_mod = types.ModuleType("open_webui.utils")
    open_webui_utils_chat_mod = types.ModuleType("open_webui.utils.chat")
    open_webui_utils_models_mod = types.ModuleType("open_webui.utils.models")

    class _Users:
        @staticmethod
        def get_user_by_id(user_id: object) -> dict[str, object]:
            return {"id": user_id}

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        return {"choices": [{"message": {"content": payload.get("_mock_content", "")}}]}

    async def _all_models(_: object, user: object = None) -> list[dict[str, str]]:
        del user
        return [{"id": "base-model"}, {"id": "prep-model"}, {"id": "pipe-model"}]

    open_webui_models_users_mod.Users = _Users
    open_webui_utils_chat_mod.generate_chat_completion = _chat_completion
    open_webui_utils_models_mod.get_all_models = _all_models

    sys.modules["fastapi"] = fastapi_mod
    sys.modules["open_webui"] = open_webui_mod
    sys.modules["open_webui.models"] = open_webui_models_mod
    sys.modules["open_webui.models.users"] = open_webui_models_users_mod
    sys.modules["open_webui.utils"] = open_webui_utils_mod
    sys.modules["open_webui.utils.chat"] = open_webui_utils_chat_mod
    sys.modules["open_webui.utils.models"] = open_webui_utils_models_mod
    if block_pydantic:
        real_import = builtins.__import__

        def _guarded_import(
            name: str,
            globals_: dict[str, object] | None = None,
            locals_: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            if name == "pydantic":
                raise ModuleNotFoundError("No module named 'pydantic'")
            return real_import(name, globals_, locals_, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", _guarded_import)

    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preprocessor_model_defaults_to_base_model(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_defaults", monkeypatch)
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = ""

    assert pipe._resolve_preprocessor_model_id("base-model") == "base-model"


def test_preprocessor_model_can_be_overridden(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_override", monkeypatch)
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"

    assert pipe._resolve_preprocessor_model_id("base-model") == "prep-model"


def test_invalid_preprocessor_model_is_normalized(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_invalid", monkeypatch)
    pipe = module.Pipe()

    async def _models(_: object, user: object = None) -> list[dict[str, str]]:
        del user
        return [{"id": "base-model"}]

    module.get_all_models = _models

    error = asyncio.run(
        pipe._validate_configured_model_ids(
            request=object(),
            user_payload={"id": "u1"},
            base_model_id="base-model",
            preprocessor_model_id="missing-prep-model",
        )
    )

    assert error == (
        "Context Compiler pipe misconfigured: PREPROCESSOR_MODEL_ID was not found "
        "in Open WebUI models."
    )


def test_preprocessor_fallback_uses_preprocessor_model_only(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_routing", monkeypatch)
    pipe = module.Pipe()

    calls: list[str] = []

    async def _chat_completion(_: object, payload: dict[str, Any], __: object) -> dict[str, object]:
        calls.append(str(payload.get("model", "")))
        # First call is fallback precompile completion; return no directive.
        # Second call is main forward passthrough.
        if len(calls) == 1:
            return {"choices": [{"message": {"content": "no_directive"}}]}
        return {"ok": True}

    async def _models(_: object, user: object = None) -> list[dict[str, str]]:
        del user
        return [{"id": "base-model"}, {"id": "prep-model"}, {"id": "pipe-model"}]

    def _heuristic(_: str) -> dict[str, object]:
        return {"outcome": "no_directive", "directive": None}

    module.generate_chat_completion = _chat_completion
    module.get_all_models = _models
    module.precompile_heuristic = _heuristic

    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"

    body = {
        "model": "pipe-model",
        "messages": [{"role": "user", "content": "please use docker"}],
    }
    result = asyncio.run(
        pipe.pipe(
            body,
            __user__={"id": "u1"},
            __request__=object(),
        )
    )

    assert result == {"ok": True}
    assert calls == ["prep-model", "base-model"]


def test_recursion_guard_for_preprocessor_model(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_recursion", monkeypatch)
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "pipe-model"

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hi"}]},
            __user__={"id": "u1"},
            __request__=object(),
        )
    )

    assert result == (
        "Context Compiler pipe misconfigured: PREPROCESSOR_MODEL_ID must not "
        "match the selected pipe model id to avoid recursive routing."
    )


def test_preprocessor_pipe_restore_and_persist_checkpoint_points(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_checkpoint", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY["chat-1"] = "ckpt-in"

    class _FakeEngine:
        def __init__(self, kind: str, checkpoint_out: str) -> None:
            self.kind = kind
            self.state = {"premise": None, "policies": {}, "version": 2}
            self.imported: list[str] = []
            self._checkpoint_out = checkpoint_out
            self.export_calls = 0

        def import_checkpoint_json(self, payload: str) -> None:
            self.imported.append(payload)

        def export_checkpoint_json(self) -> str:
            self.export_calls += 1
            return self._checkpoint_out

        def step(self, _text: str) -> dict[str, object]:
            if self.kind == "clarify":
                return {"kind": "clarify", "prompt_to_user": "confirm?", "state": None}
            return {"kind": self.kind, "state": self.state}

    created: list[_FakeEngine] = []

    def _create_engine():
        engine = _FakeEngine("clarify", "ckpt-clarify")
        created.append(engine)
        return engine

    monkeypatch.setattr(module, "create_engine", _create_engine)
    monkeypatch.setattr(module, "precompile_heuristic", lambda _text: {"outcome": "no_directive"})
    monkeypatch.setattr(module, "parse_precompiler_output", lambda _value: None)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "test"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-1",
        )
    )
    assert result == "confirm?"
    assert created[0].imported == ["ckpt-in"]
    assert module._CHECKPOINTS_BY_CHAT_KEY["chat-1"] == "ckpt-clarify"
    assert created[0].export_calls == 1

    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY["chat-2"] = "ckpt-keep"

    passthrough_engine = _FakeEngine("passthrough", "ckpt-new")
    monkeypatch.setattr(module, "create_engine", lambda: passthrough_engine)
    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-2",
        )
    )
    assert isinstance(result, dict)
    assert passthrough_engine.imported == ["ckpt-keep"]
    assert passthrough_engine.export_calls == 0
    assert module._CHECKPOINTS_BY_CHAT_KEY["chat-2"] == "ckpt-keep"
