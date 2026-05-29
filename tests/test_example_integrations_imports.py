import builtins
import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
INTEGRATIONS_DIR = REPO_ROOT / "examples" / "integrations"


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _install_openwebui_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    fastapi_mod = types.ModuleType("fastapi")

    class _Request:
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

    monkeypatch.setitem(sys.modules, "fastapi", fastapi_mod)
    monkeypatch.setitem(sys.modules, "open_webui", open_webui_mod)
    monkeypatch.setitem(sys.modules, "open_webui.models", open_webui_models_mod)
    monkeypatch.setitem(sys.modules, "open_webui.models.users", open_webui_models_users_mod)
    monkeypatch.setitem(sys.modules, "open_webui.utils", open_webui_utils_mod)
    monkeypatch.setitem(sys.modules, "open_webui.utils.chat", open_webui_utils_chat_mod)
    monkeypatch.setitem(sys.modules, "open_webui.utils.models", open_webui_utils_models_mod)


def _block_optional_imports(
    monkeypatch: pytest.MonkeyPatch, blocked_prefixes: tuple[str, ...]
) -> None:
    real_import = builtins.__import__

    def _guarded_import(
        name: str,
        globals_: dict[str, object] | None = None,
        locals_: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in blocked_prefixes):
            raise ModuleNotFoundError(f"No module named '{name}'")
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _guarded_import)


@pytest.mark.parametrize(
    ("module_path", "blocked_prefixes", "needs_openwebui_stubs"),
    [
        (INTEGRATIONS_DIR / "litellm" / "basic.py", ("litellm",), False),
        (INTEGRATIONS_DIR / "litellm" / "with_preprocessor.py", ("litellm",), False),
        (
            INTEGRATIONS_DIR / "ollama_structured_output" / "example.py",
            (),
            False,
        ),
        (
            INTEGRATIONS_DIR / "litellm_proxy" / "context_compiler_precall_hook.py",
            ("litellm",),
            False,
        ),
        (
            INTEGRATIONS_DIR
            / "litellm_proxy"
            / "context_compiler_precall_hook_with_preprocessor.py",
            ("litellm",),
            False,
        ),
        (INTEGRATIONS_DIR / "openwebui" / "open_webui_pipe.py", ("pydantic",), True),
        (
            INTEGRATIONS_DIR / "openwebui" / "open_webui_pipe_with_preprocessor.py",
            ("pydantic",),
            True,
        ),
    ],
)
def test_example_integration_modules_import_without_optional_dependencies(
    module_path: Path,
    blocked_prefixes: tuple[str, ...],
    needs_openwebui_stubs: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if needs_openwebui_stubs:
        _install_openwebui_stubs(monkeypatch)
    _block_optional_imports(monkeypatch, blocked_prefixes)

    module = _load_module(f"test_import_{module_path.stem}", module_path)
    assert module is not None
