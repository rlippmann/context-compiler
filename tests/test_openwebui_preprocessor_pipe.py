import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

MODULE_PATH = Path("examples/integrations/openwebui/open_webui_pipe_with_preprocessor.py")


def _load_module_with_openwebui_stubs(module_name: str):
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

    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preprocessor_model_defaults_to_base_model() -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_defaults")
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = ""

    assert pipe._resolve_preprocessor_model_id("base-model") == "base-model"


def test_preprocessor_model_can_be_overridden() -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_override")
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"

    assert pipe._resolve_preprocessor_model_id("base-model") == "prep-model"


def test_invalid_preprocessor_model_is_normalized() -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_invalid")
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


def test_preprocessor_fallback_uses_preprocessor_model_only() -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_routing")
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


def test_recursion_guard_for_preprocessor_model() -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_recursion")
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
