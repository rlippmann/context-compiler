import importlib.util
import types
from pathlib import Path
from typing import Any

import pytest

from context_compiler import create_engine

LITELLM_BASIC_PATH = Path("examples/integrations/litellm/basic.py")
LITELLM_WITH_PREPROC_PATH = Path("examples/integrations/litellm/with_preprocessor.py")


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _patch_completion_loader(monkeypatch, module: object, completion_fn: Any) -> None:
    if hasattr(module, "_get_litellm_completion"):
        monkeypatch.setattr(module, "_get_litellm_completion", lambda: completion_fn)
        return

    module_proxy = types.SimpleNamespace(completion=completion_fn)
    monkeypatch.setattr(module, "import_module", lambda _: module_proxy)  # type: ignore[misc]


@pytest.mark.parametrize(
    ("module_name", "path"),
    [
        ("litellm_basic_error_paths", LITELLM_BASIC_PATH),
        ("litellm_with_preproc_error_paths", LITELLM_WITH_PREPROC_PATH),
    ],
)
def test_call_litellm_requires_api_key(monkeypatch, module_name: str, path: Path) -> None:
    module = _load_module(module_name, path)
    monkeypatch.delenv("PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _patch_completion_loader(monkeypatch, module, lambda **_: {})

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required in openai mode"):
        module._call_litellm([{"role": "user", "content": "hello"}])


@pytest.mark.parametrize(
    ("module_name", "path"),
    [
        ("litellm_basic_missing_dep", LITELLM_BASIC_PATH),
        ("litellm_with_preproc_missing_dep", LITELLM_WITH_PREPROC_PATH),
    ],
)
def test_call_litellm_requires_litellm_dependency(
    monkeypatch, module_name: str, path: Path
) -> None:
    module = _load_module(module_name, path)
    monkeypatch.delenv("PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    def _raise_module_not_found() -> Any:
        raise ModuleNotFoundError

    if hasattr(module, "_get_litellm_completion"):
        monkeypatch.setattr(module, "_get_litellm_completion", _raise_module_not_found)
    else:
        monkeypatch.setattr(
            module,
            "import_module",
            lambda _: _raise_module_not_found(),
        )

    with pytest.raises(RuntimeError, match="litellm is required"):
        module._call_litellm([{"role": "user", "content": "hello"}])


@pytest.mark.parametrize(
    ("module_name", "path"),
    [
        ("litellm_basic_malformed_response", LITELLM_BASIC_PATH),
        ("litellm_with_preproc_malformed_response", LITELLM_WITH_PREPROC_PATH),
    ],
)
def test_call_litellm_rejects_missing_content_shape(
    monkeypatch, module_name: str, path: Path
) -> None:
    module = _load_module(module_name, path)
    monkeypatch.delenv("PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    def _completion(**_: Any) -> dict[str, object]:
        return {"choices": [{"message": {"content": None}}]}

    _patch_completion_loader(monkeypatch, module, _completion)

    with pytest.raises(
        RuntimeError, match="LiteLLM response missing choices\\[0\\]\\.message\\.content"
    ):
        module._call_litellm([{"role": "user", "content": "hello"}])


@pytest.mark.parametrize(
    ("module_name", "path"),
    [
        ("litellm_basic_provider_unknown", LITELLM_BASIC_PATH),
        ("litellm_with_preproc_provider_unknown", LITELLM_WITH_PREPROC_PATH),
    ],
)
def test_call_litellm_rejects_unknown_provider(monkeypatch, module_name: str, path: Path) -> None:
    module = _load_module(module_name, path)
    monkeypatch.setenv("PROVIDER", "bedrock")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    _patch_completion_loader(monkeypatch, module, lambda **_: {})

    with pytest.raises(
        RuntimeError,
        match=(
            "Invalid PROVIDER value 'bedrock'. Allowed values: openai, ollama, openai_compatible"
        ),
    ):
        module._call_litellm([{"role": "user", "content": "hello"}])


@pytest.mark.parametrize(
    ("module_name", "path"),
    [
        ("litellm_basic_openai_compatible_missing_base", LITELLM_BASIC_PATH),
        ("litellm_with_preproc_openai_compatible_missing_base", LITELLM_WITH_PREPROC_PATH),
    ],
)
def test_call_litellm_openai_compatible_requires_base_url(
    monkeypatch, module_name: str, path: Path
) -> None:
    module = _load_module(module_name, path)
    monkeypatch.setenv("PROVIDER", "openai_compatible")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _patch_completion_loader(monkeypatch, module, lambda **_: {})

    with pytest.raises(
        RuntimeError, match="OPENAI_BASE_URL is required when PROVIDER=openai_compatible."
    ):
        module._call_litellm([{"role": "user", "content": "hello"}])


@pytest.mark.parametrize(
    ("module_name", "path"),
    [
        ("litellm_basic_ollama_optional_key", LITELLM_BASIC_PATH),
        ("litellm_with_preproc_ollama_optional_key", LITELLM_WITH_PREPROC_PATH),
    ],
)
def test_call_litellm_ollama_mode_allows_missing_api_key(
    monkeypatch, module_name: str, path: Path
) -> None:
    module = _load_module(module_name, path)
    seen: dict[str, object] = {}

    def _completion(**kwargs: Any) -> dict[str, object]:
        seen.update(kwargs)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setenv("PROVIDER", "ollama")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _patch_completion_loader(monkeypatch, module, _completion)

    result = module._call_litellm([{"role": "user", "content": "hello"}])
    assert result == "ok"
    assert seen["api_base"] == "http://localhost:11434"
    assert "api_key" not in seen


@pytest.mark.parametrize(
    ("module_name", "path"),
    [
        ("litellm_basic_base_url_override", LITELLM_BASIC_PATH),
        ("litellm_with_preproc_base_url_override", LITELLM_WITH_PREPROC_PATH),
    ],
)
def test_call_litellm_base_url_override_wins_over_provider(
    monkeypatch, module_name: str, path: Path
) -> None:
    module = _load_module(module_name, path)
    seen: dict[str, object] = {}

    def _completion(**kwargs: Any) -> dict[str, object]:
        seen.update(kwargs)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setenv("PROVIDER", "ollama")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.compat/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _patch_completion_loader(monkeypatch, module, _completion)

    result = module._call_litellm([{"role": "user", "content": "hello"}])
    assert result == "ok"
    assert seen["api_base"] == "https://example.compat/v1"
    assert "api_key" not in seen


def test_call_litellm_logs_single_mode_resolution_line(
    monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    import host_support.provider_mode as _provider

    module = _load_module("litellm_basic_logs_resolution", LITELLM_BASIC_PATH)
    _provider._STARTUP_LOGGED = False

    def _completion(**_: Any) -> dict[str, object]:
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setenv("MODEL", "openai/demo-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("PROVIDER", "ollama")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _patch_completion_loader(monkeypatch, module, _completion)

    with caplog.at_level("INFO"):
        first = module._call_litellm([{"role": "user", "content": "hello"}])
        second = module._call_litellm([{"role": "user", "content": "again"}])

    assert first == "ok"
    assert second == "ok"
    matches = [
        rec
        for rec in caplog.records
        if rec.getMessage().startswith("litellm_config mode=openai_compatible")
    ]
    assert len(matches) == 1
    message = matches[0].getMessage()
    assert "base_url=http://localhost:11434/v1" in message
    assert "model=openai/demo-model" in message
    assert "source=OPENAI_BASE_URL override" in message


def test_with_preprocessor_fallback_failure_preserves_basic_behavior(monkeypatch) -> None:
    module = _load_module("litellm_with_preproc_fallback_failure", LITELLM_WITH_PREPROC_PATH)

    seen_preprocess_inputs: list[str] = []

    def _heuristic(_text: str) -> dict[str, object]:
        return {"outcome": "no_directive", "directive": None}

    def _fallback(_message: str, _state: dict[str, object]) -> str | None:
        seen_preprocess_inputs.append("called")
        raise RuntimeError("fallback failed")

    seen_engine_inputs: list[str] = []

    class _ProxyEngine:
        def __init__(self) -> None:
            self._engine = create_engine()

        @property
        def state(self) -> dict[str, object]:
            return self._engine.state

        def export_checkpoint(self) -> dict[str, object]:
            return self._engine.export_checkpoint()

        def has_pending_clarification(self) -> bool:
            return self._engine.has_pending_clarification()

        def step(self, text: str) -> dict[str, object]:
            seen_engine_inputs.append(text)
            return self._engine.step(text)

    monkeypatch.setattr(module, "preprocess_heuristic", _heuristic)
    monkeypatch.setattr(module, "_llm_fallback_preprocess", _fallback)
    monkeypatch.setattr(module, "_call_litellm", lambda _messages: "ok")

    engine = _ProxyEngine()
    result = module.handle_turn("hello world", engine)

    assert result == "ok"
    assert seen_preprocess_inputs == ["called"]
    assert seen_engine_inputs == ["hello world"]
