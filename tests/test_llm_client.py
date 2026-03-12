import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import demos.llm_client as llm_client  # noqa: E402
from demos.llm_client import DemoLLMError, LLMConfig, complete_messages  # noqa: E402


def _fake_config() -> LLMConfig:
    return LLMConfig(base_url="http://localhost:11434/v1", api_key="test-key", model="bad-model")


class _FakeCompletions:
    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = outcomes
        self._index = 0

    def create(self, **_kwargs: object) -> object:
        if self._index >= len(self._outcomes):
            raise RuntimeError("No more fake outcomes configured.")
        outcome = self._outcomes[self._index]
        self._index += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeChat:
    def __init__(self, outcomes: list[object]) -> None:
        self.completions = _FakeCompletions(outcomes)


class _FakeClient:
    def __init__(self, outcomes: list[object]) -> None:
        self.chat = _FakeChat(outcomes)


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
        "_build_openai_client",
        lambda _config: _FakeClient([RuntimeError("model not found")]),
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
        "_build_openai_client",
        lambda _config: _FakeClient([RuntimeError("invalid api key")]),
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
        "_build_openai_client",
        lambda _config: _FakeClient(
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
        "_build_openai_client",
        lambda _config: _FakeClient(
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
        "_build_openai_client",
        lambda _config: _FakeClient([_FakeRateLimitError("rate limit exceeded", retry_after="10")]),
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
        "_build_openai_client",
        lambda _config: _FakeClient(
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
        "_build_openai_client",
        lambda _config: _FakeClient(
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
