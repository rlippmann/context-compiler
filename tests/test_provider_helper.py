import logging

import pytest

import host_support.provider_mode as _provider


def test_resolve_provider_config_defaults_to_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.delenv("MODEL", raising=False)

    config = _provider.resolve_provider_config(default_model="gpt-4.1-mini")

    assert config.mode == "openai"
    assert config.source == "default"
    assert config.base_url == "https://api.openai.com/v1"
    assert config.model == "gpt-4.1-mini"
    assert config.api_key == "dummy"


def test_resolve_provider_config_base_url_override_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROVIDER", "ollama")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.compat/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MODEL", "openai/my-model")

    config = _provider.resolve_provider_config(default_model="ignored")

    assert config.mode == "openai_compatible"
    assert config.source == "OPENAI_BASE_URL override"
    assert config.base_url == "https://example.compat/v1"
    assert config.model == "openai/my-model"
    assert config.api_key is None


def test_resolve_provider_config_rejects_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROVIDER", "bedrock")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    with pytest.raises(
        RuntimeError,
        match="Invalid PROVIDER value 'bedrock'. Allowed values: openai, ollama, openai_compatible",
    ):
        _provider.resolve_provider_config()


def test_resolve_provider_config_openai_compatible_requires_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROVIDER", "openai_compatible")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(
        RuntimeError, match="OPENAI_BASE_URL is required when PROVIDER=openai_compatible."
    ):
        _provider.resolve_provider_config()


def test_resolve_provider_config_openai_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required in openai mode."):
        _provider.resolve_provider_config()


def test_resolve_provider_config_ollama_mode_returns_expected_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROVIDER", "ollama")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MODEL", "openai/custom-ollama-model")

    config = _provider.resolve_provider_config(default_model="ignored")

    assert config.mode == "ollama"
    assert config.source == "PROVIDER"
    assert config.base_url == "http://localhost:11434"
    assert config.model == "openai/custom-ollama-model"
    assert config.api_key is None


def test_print_startup_config_logs_once(monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("MODEL", "openai/demo-model")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _provider._STARTUP_LOGGED = False

    config = _provider.resolve_provider_config(default_model="ignored")
    logger = logging.getLogger("provider_helper_test")

    with caplog.at_level("INFO", logger="provider_helper_test"):
        _provider.print_startup_config(config, logger=logger)
        _provider.print_startup_config(config, logger=logger)

    matches = [
        rec
        for rec in caplog.records
        if rec.getMessage().startswith("litellm_config mode=openai_compatible")
    ]
    assert len(matches) == 1
