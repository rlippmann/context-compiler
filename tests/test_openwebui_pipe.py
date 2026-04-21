import builtins
import importlib.util
import sys
import types
from pathlib import Path

MODULE_PATH = Path("examples/integrations/openwebui/open_webui_pipe.py")


def _load_module_with_openwebui_stubs(module_name: str, monkeypatch):
    fastapi_mod = types.ModuleType("fastapi")

    class _Request:
        pass

    fastapi_mod.Request = _Request

    open_webui_mod = types.ModuleType("open_webui")
    open_webui_models_mod = types.ModuleType("open_webui.models")
    open_webui_models_users_mod = types.ModuleType("open_webui.models.users")
    open_webui_utils_mod = types.ModuleType("open_webui.utils")
    open_webui_utils_chat_mod = types.ModuleType("open_webui.utils.chat")

    class _Users:
        @staticmethod
        def get_user_by_id(user_id: object) -> dict[str, object]:
            return {"id": user_id}

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        return {"choices": [{"message": {"content": payload.get("_mock_content", "")}}]}

    open_webui_models_users_mod.Users = _Users
    open_webui_utils_chat_mod.generate_chat_completion = _chat_completion

    sys.modules["fastapi"] = fastapi_mod
    sys.modules["open_webui"] = open_webui_mod
    sys.modules["open_webui.models"] = open_webui_models_mod
    sys.modules["open_webui.models.users"] = open_webui_models_users_mod
    sys.modules["open_webui.utils"] = open_webui_utils_mod
    sys.modules["open_webui.utils.chat"] = open_webui_utils_chat_mod

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


def test_openwebui_pipe_imports_without_pydantic(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_no_pydantic", monkeypatch)
    pipe = module.Pipe()
    assert pipe.valves.BASE_MODEL_ID == ""
