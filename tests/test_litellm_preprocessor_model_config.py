import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

LITELLM_WITH_PREPROC_PATH = Path("examples/integrations/litellm/with_preprocessor.py")
LITELLM_PROXY_WITH_PREPROC_PATH = Path(
    "examples/integrations/litellm_proxy/context_compiler_precall_hook_with_preprocessor.py"
)


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_litellm_proxy_module_with_stubs(monkeypatch, module_name: str):
    litellm_mod = types.ModuleType("litellm")
    integrations_mod = types.ModuleType("litellm.integrations")
    custom_logger_mod = types.ModuleType("litellm.integrations.custom_logger")

    class _CustomLogger:
        pass

    custom_logger_mod.CustomLogger = _CustomLogger

    monkeypatch.setitem(sys.modules, "litellm", litellm_mod)
    monkeypatch.setitem(sys.modules, "litellm.integrations", integrations_mod)
    monkeypatch.setitem(sys.modules, "litellm.integrations.custom_logger", custom_logger_mod)

    return _load_module(module_name, LITELLM_PROXY_WITH_PREPROC_PATH)


def test_litellm_preprocessor_model_defaults_to_model(monkeypatch):
    module = _load_module("litellm_with_preproc_cfg_default", LITELLM_WITH_PREPROC_PATH)

    seen: dict[str, Any] = {}

    def _completion(**kwargs):
        seen["model"] = kwargs["model"]
        return {"choices": [{"message": {"content": "use docker"}}]}

    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setenv("MODEL", "openai/main-model")
    monkeypatch.delenv("PREPROCESSOR_MODEL", raising=False)

    monkeypatch.setattr(module, "_get_litellm_completion", lambda: _completion)
    monkeypatch.setattr(module, "render_prompt", lambda *_: "prompt")
    monkeypatch.setattr(module, "parse_precompiler_output", lambda value: value)

    result = module._llm_fallback_precompile("please use docker", None)

    assert result == "use docker"
    assert seen["model"] == "openai/main-model"


def test_litellm_preprocessor_model_override(monkeypatch):
    module = _load_module("litellm_with_preproc_cfg_override", LITELLM_WITH_PREPROC_PATH)

    seen: dict[str, Any] = {}

    def _completion(**kwargs):
        seen["model"] = kwargs["model"]
        return {"choices": [{"message": {"content": "use docker"}}]}

    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setenv("MODEL", "openai/main-model")
    monkeypatch.setenv("PREPROCESSOR_MODEL", "openai/preprocessor-model")

    monkeypatch.setattr(module, "_get_litellm_completion", lambda: _completion)
    monkeypatch.setattr(module, "render_prompt", lambda *_: "prompt")
    monkeypatch.setattr(module, "parse_precompiler_output", lambda value: value)

    result = module._llm_fallback_precompile("please use docker", None)

    assert result == "use docker"
    assert seen["model"] == "openai/preprocessor-model"


def test_litellm_proxy_preprocessor_model_defaults_to_model(monkeypatch):
    module = _load_litellm_proxy_module_with_stubs(
        monkeypatch, "litellm_proxy_with_preproc_cfg_default"
    )

    seen: dict[str, Any] = {}

    def _completion(**kwargs):
        seen["model"] = kwargs["model"]
        return {"choices": [{"message": {"content": "use docker"}}]}

    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setenv("MODEL", "openai/main-model")
    monkeypatch.delenv("PREPROCESSOR_MODEL", raising=False)

    monkeypatch.setattr(module, "_get_litellm_completion", lambda: _completion)
    monkeypatch.setattr(module, "render_prompt", lambda *_: "prompt")
    monkeypatch.setattr(module, "parse_precompiler_output", lambda value: value)

    result = module._llm_fallback_precompile("please use docker", None)

    assert result == "use docker"
    assert seen["model"] == "openai/main-model"


def test_litellm_proxy_preprocessor_model_override(monkeypatch):
    module = _load_litellm_proxy_module_with_stubs(
        monkeypatch, "litellm_proxy_with_preproc_cfg_override"
    )

    seen: dict[str, Any] = {}

    def _completion(**kwargs):
        seen["model"] = kwargs["model"]
        return {"choices": [{"message": {"content": "use docker"}}]}

    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setenv("MODEL", "openai/main-model")
    monkeypatch.setenv("PREPROCESSOR_MODEL", "openai/preprocessor-model")

    monkeypatch.setattr(module, "_get_litellm_completion", lambda: _completion)
    monkeypatch.setattr(module, "render_prompt", lambda *_: "prompt")
    monkeypatch.setattr(module, "parse_precompiler_output", lambda value: value)

    result = module._llm_fallback_precompile("please use docker", None)

    assert result == "use docker"
    assert seen["model"] == "openai/preprocessor-model"


def test_litellm_fallback_rejects_premise_near_miss_rewrite(monkeypatch):
    module = _load_module(
        "litellm_with_preproc_cfg_reject_premise_rewrite", LITELLM_WITH_PREPROC_PATH
    )

    def _completion(**kwargs):
        del kwargs
        return {"choices": [{"message": {"content": "set premise concise replies"}}]}

    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setenv("MODEL", "openai/main-model")
    monkeypatch.delenv("PREPROCESSOR_MODEL", raising=False)

    monkeypatch.setattr(module, "_get_litellm_completion", lambda: _completion)
    monkeypatch.setattr(module, "render_prompt", lambda *_: "prompt")
    monkeypatch.setattr(module, "parse_precompiler_output", lambda value: value)

    result = module._llm_fallback_precompile("set premise to concise replies", None)
    assert result is None


def test_litellm_proxy_fallback_rejects_premise_near_miss_rewrite(monkeypatch):
    module = _load_litellm_proxy_module_with_stubs(
        monkeypatch, "litellm_proxy_with_preproc_cfg_reject_premise_rewrite"
    )

    def _completion(**kwargs):
        del kwargs
        return {"choices": [{"message": {"content": "change premise to concise replies"}}]}

    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setenv("MODEL", "openai/main-model")
    monkeypatch.delenv("PREPROCESSOR_MODEL", raising=False)

    monkeypatch.setattr(module, "_get_litellm_completion", lambda: _completion)
    monkeypatch.setattr(module, "render_prompt", lambda *_: "prompt")
    monkeypatch.setattr(module, "parse_precompiler_output", lambda value: value)

    result = module._llm_fallback_precompile("change premise concise replies", None)
    assert result is None
