import sys
from contextlib import contextmanager
from pathlib import Path

import litellm
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import demos.llm_client as llm_client  # noqa: E402
from demos.llm_client import DemoLLMError, LLMConfig, complete_messages  # noqa: E402


def _fake_config() -> LLMConfig:
    return LLMConfig(base_url="http://localhost:11434/v1", api_key="test-key", model="bad-model")


class _FakeLiteLLMCompletion:
    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = outcomes
        self._index = 0

    def __call__(self, **_kwargs: object) -> object:
        if self._index >= len(self._outcomes):
            raise RuntimeError("No more fake outcomes configured.")
        outcome = self._outcomes[self._index]
        self._index += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _RecordingLiteLLMCompletion:
    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = outcomes
        self._index = 0
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self._index >= len(self._outcomes):
            raise RuntimeError("No more fake outcomes configured.")
        outcome = self._outcomes[self._index]
        self._index += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeRateLimitError(RuntimeError):
    def __init__(self, message: str, retry_after: str | None = None) -> None:
        super().__init__(message)
        if retry_after is None:
            self.response = None
            return
        self.response = type(
            "Response",
            (),
            {"headers": {"retry-after": retry_after}},
        )()


def test_complete_messages_maps_model_not_found_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_client, "load_config", _fake_config)
    monkeypatch.setattr(
        llm_client,
        "_litellm_completion",
        _FakeLiteLLMCompletion([RuntimeError("model not found")]),
    )

    with pytest.raises(DemoLLMError) as exc_info:
        complete_messages([{"role": "user", "content": "hello"}])

    assert str(exc_info.value) == (
        "Model 'bad-model' was not found at the configured endpoint. "
        "Check MODEL or OPENAI_BASE_URL."
    )


def test_complete_messages_maps_authentication_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_client, "load_config", _fake_config)
    monkeypatch.setattr(
        llm_client,
        "_litellm_completion",
        _FakeLiteLLMCompletion([RuntimeError("invalid api key")]),
    )

    with pytest.raises(DemoLLMError) as exc_info:
        complete_messages([{"role": "user", "content": "hello"}])

    assert str(exc_info.value) == "Authentication failed. Check OPENAI_API_KEY."


def test_complete_messages_retries_rate_limit_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(llm_client, "load_config", _fake_config)
    monkeypatch.setattr(
        llm_client,
        "_litellm_completion",
        _FakeLiteLLMCompletion(
            [
                RuntimeError("rate limit exceeded"),
                RuntimeError("rate limit exceeded"),
                _FakeResponse("ok"),
            ]
        ),
    )
    delays: list[int] = []
    monkeypatch.setattr(llm_client.time, "sleep", lambda seconds: delays.append(seconds))

    result = complete_messages([{"role": "user", "content": "hello"}])
    stderr = capsys.readouterr().err

    assert result == "ok"
    assert delays == [1, 2]
    assert "[retry] LLM rate limit hit — retrying in 1s..." in stderr
    assert "[retry] LLM rate limit hit — retrying in 2s..." in stderr


def test_complete_messages_rate_limit_exhausted_raises_friendly_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(llm_client, "load_config", _fake_config)
    monkeypatch.setattr(
        llm_client,
        "_litellm_completion",
        _FakeLiteLLMCompletion(
            [
                _FakeRateLimitError("rate limit exceeded"),
                _FakeRateLimitError("rate limit exceeded"),
                _FakeRateLimitError("rate limit exceeded"),
                _FakeRateLimitError("rate limit exceeded"),
            ]
        ),
    )
    delays: list[int] = []
    monkeypatch.setattr(llm_client.time, "sleep", lambda seconds: delays.append(seconds))

    with pytest.raises(DemoLLMError) as exc_info:
        complete_messages([{"role": "user", "content": "hello"}])
    stderr = capsys.readouterr().err

    assert delays == [1, 2, 4]
    assert (
        str(exc_info.value)
        == "LLM provider rate limit exceeded. Try again later or switch providers."
    )
    assert "[retry] LLM rate limit hit — retrying in 1s..." in stderr
    assert "[retry] LLM rate limit hit — retrying in 2s..." in stderr
    assert "[retry] LLM rate limit hit — retrying in 4s..." in stderr


def test_complete_messages_long_retry_after_fails_fast(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(llm_client, "load_config", _fake_config)
    monkeypatch.setattr(
        llm_client,
        "_litellm_completion",
        _FakeLiteLLMCompletion([_FakeRateLimitError("rate limit exceeded", retry_after="10")]),
    )
    delays: list[int] = []
    monkeypatch.setattr(llm_client.time, "sleep", lambda seconds: delays.append(seconds))

    with pytest.raises(DemoLLMError) as exc_info:
        complete_messages([{"role": "user", "content": "hello"}])
    stderr = capsys.readouterr().err

    assert delays == []
    assert "[retry]" not in stderr
    assert str(exc_info.value) == (
        "LLM provider requested retry after 10s, which exceeds the demo retry limit. "
        "Try again later or switch providers."
    )


def test_complete_messages_uses_gemini_retry_in_text_delay(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(llm_client, "load_config", _fake_config)
    monkeypatch.setattr(
        llm_client,
        "_litellm_completion",
        _FakeLiteLLMCompletion(
            [RuntimeError("Please retry in 1.311529971s."), _FakeResponse("ok")]
        ),
    )
    delays: list[int] = []
    monkeypatch.setattr(llm_client.time, "sleep", lambda seconds: delays.append(seconds))

    result = complete_messages([{"role": "user", "content": "hello"}])
    stderr = capsys.readouterr().err

    assert result == "ok"
    assert delays == [2]
    assert "[retry] LLM rate limit hit — retrying in 2s..." in stderr


def test_complete_messages_uses_gemini_retry_delay_field(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(llm_client, "load_config", _fake_config)
    monkeypatch.setattr(
        llm_client,
        "_litellm_completion",
        _FakeLiteLLMCompletion(
            [RuntimeError("rate limit exceeded, retryDelay: '1s'"), _FakeResponse("ok")]
        ),
    )
    delays: list[int] = []
    monkeypatch.setattr(llm_client.time, "sleep", lambda seconds: delays.append(seconds))

    result = complete_messages([{"role": "user", "content": "hello"}])
    stderr = capsys.readouterr().err

    assert result == "ok"
    assert delays == [1]
    assert "[retry] LLM rate limit hit — retrying in 1s..." in stderr


def test_complete_messages_applies_delay_seconds_before_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_client, "load_config", _fake_config)
    monkeypatch.setattr(
        llm_client,
        "_litellm_completion",
        _FakeLiteLLMCompletion([_FakeResponse("ok")]),
    )
    delays: list[float] = []
    monkeypatch.setattr(llm_client.time, "sleep", lambda seconds: delays.append(seconds))

    result = complete_messages([{"role": "user", "content": "hello"}], delay_seconds=1.5)

    assert result == "ok"
    assert delays == [1.5]


def test_complete_messages_supports_dict_style_litellm_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_client, "load_config", _fake_config)
    monkeypatch.setattr(
        llm_client,
        "_litellm_completion",
        _FakeLiteLLMCompletion([{"choices": [{"message": {"content": "ok"}}]}]),
    )

    result = complete_messages([{"role": "user", "content": "hello"}])

    assert result == "ok"


def test_complete_messages_normal_path_uses_deterministic_decoding_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_client, "load_config", _fake_config)
    fake_completion = _RecordingLiteLLMCompletion([_FakeResponse("ok")])
    monkeypatch.setattr(llm_client, "_litellm_completion", fake_completion)

    result = complete_messages([{"role": "user", "content": "hello"}])

    assert result == "ok"
    assert len(fake_completion.calls) == 1
    assert fake_completion.calls[0]["deterministic_decoding"] is True


def test_complete_messages_retries_once_without_temperature_on_unsupported_param(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(llm_client, "load_config", _fake_config)
    monkeypatch.setenv("CONTEXT_COMPILER_DEMO_VERBOSE", "1")
    drop_params_scopes: list[bool] = []

    @contextmanager
    def fake_drop_params_scope(enabled: bool):
        drop_params_scopes.append(enabled)
        yield

    monkeypatch.setattr(llm_client, "_temporary_litellm_drop_params", fake_drop_params_scope)
    fake_completion = _RecordingLiteLLMCompletion(
        [
            litellm.UnsupportedParamsError(
                message="temperature is not supported",
                model="bad-model",
                llm_provider="openai",
            ),
            _FakeResponse("ok"),
        ]
    )
    monkeypatch.setattr(llm_client, "_litellm_completion", fake_completion)

    result = complete_messages([{"role": "user", "content": "hello"}])
    stderr = capsys.readouterr().err

    assert result == "ok"
    assert len(fake_completion.calls) == 2
    assert fake_completion.calls[0]["deterministic_decoding"] is True
    assert fake_completion.calls[1]["deterministic_decoding"] is False
    assert drop_params_scopes == [False, True]
    assert "[fallback] model rejected deterministic decoding params;" in stderr


def test_complete_messages_fallback_failure_surfaces_existing_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_client, "load_config", _fake_config)
    drop_params_scopes: list[bool] = []

    @contextmanager
    def fake_drop_params_scope(enabled: bool):
        drop_params_scopes.append(enabled)
        yield

    monkeypatch.setattr(llm_client, "_temporary_litellm_drop_params", fake_drop_params_scope)
    fake_completion = _RecordingLiteLLMCompletion(
        [
            litellm.UnsupportedParamsError(
                message="temperature is not supported",
                model="bad-model",
                llm_provider="openai",
            ),
            RuntimeError("provider unavailable"),
        ]
    )
    monkeypatch.setattr(llm_client, "_litellm_completion", fake_completion)

    with pytest.raises(DemoLLMError) as exc_info:
        complete_messages([{"role": "user", "content": "hello"}])

    assert "provider unavailable" in str(exc_info.value)
    assert len(fake_completion.calls) == 2
    assert fake_completion.calls[0]["deterministic_decoding"] is True
    assert fake_completion.calls[1]["deterministic_decoding"] is False
    assert drop_params_scopes == [False, True]
