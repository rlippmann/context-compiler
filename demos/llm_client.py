"""Small OpenAI-compatible chat client for demo scripts."""

import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from importlib import import_module
from typing import Any, Literal, TypedDict


class Message(TypedDict):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


@dataclass(frozen=True)
class LLMConfig:
    base_url: str | None
    api_key: str
    model: str


@dataclass(frozen=True)
class MissingDemoConfigError(RuntimeError):
    missing: list[str]
    base_url: str | None

    def __str__(self) -> str:
        missing_text = ", ".join(self.missing)
        return f"Missing demo configuration: {missing_text}"


class DemoLLMError(RuntimeError):
    """Friendly provider/client error for demos."""


_RETRY_DELAYS_SECONDS = (1, 2, 4)
MAX_DEMO_RETRY_AFTER_SECONDS = 5


def _is_model_not_found(exc_text: str, exc_name: str) -> bool:
    return (
        "notfound" in exc_name
        or "model not found" in exc_text
        or "does not exist" in exc_text
        or "unknown model" in exc_text
    )


def _is_authentication_error(exc_text: str, exc_name: str) -> bool:
    return (
        "authentication" in exc_name
        or "invalid api key" in exc_text
        or "unauthorized" in exc_text
        or "401" in exc_text
    )


def _is_permission_error(exc_text: str, exc_name: str) -> bool:
    return "permission" in exc_name or "access denied" in exc_text or "forbidden" in exc_text


def _is_rate_limit_error(exc_text: str, exc_name: str) -> bool:
    return (
        "ratelimit" in exc_name
        or "rate limit" in exc_text
        or "quota" in exc_text
        or "retrydelay" in exc_text
        or "retry in " in exc_text
    )


def _is_timeout_error(exc_text: str, exc_name: str) -> bool:
    return "timeout" in exc_name or "timed out" in exc_text


def _is_connection_error(exc_text: str, exc_name: str) -> bool:
    return (
        "apiconnection" in exc_name
        or "connection" in exc_text
        or "unreachable" in exc_text
        or "temporary failure" in exc_text
    )


def _retry_after_seconds(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    raw_value = headers.get("retry-after")
    if raw_value is None:
        raw_value = headers.get("Retry-After")
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    try:
        retry_after_time = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if retry_after_time.tzinfo is None:
        retry_after_time = retry_after_time.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    delta = (retry_after_time - now).total_seconds()
    if delta <= 0:
        return 0
    return int(delta)


def _retry_after_seconds_from_text(exc_text: str) -> int | None:
    patterns = (
        r"retry in\s+([0-9]+(?:\.[0-9]+)?)s",
        r"retrydelay\s*[:=]\s*['\"]?([0-9]+(?:\.[0-9]+)?)s['\"]?",
    )
    lowered = exc_text.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match is None:
            continue
        try:
            delay_value = float(match.group(1))
        except (TypeError, ValueError):
            continue
        if delay_value <= 0:
            return 0
        return int(delay_value) if delay_value.is_integer() else int(delay_value) + 1
    return None


def load_config() -> LLMConfig:
    """Load OpenAI-compatible configuration from environment variables."""
    base_url = os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("MODEL", "gpt-4.1-mini")

    missing: list[str] = []
    if not api_key:
        missing.append("OPENAI_API_KEY")
    if missing:
        raise MissingDemoConfigError(missing=missing, base_url=base_url)

    assert api_key is not None
    return LLMConfig(base_url=base_url, api_key=api_key, model=model)


def _build_openai_client(config: LLMConfig) -> Any:
    try:
        openai_module = import_module("openai")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The demo scripts require the demos dependency group.\n"
            "Install it with:\n"
            "pip install -e .[demos]"
        ) from exc

    client_cls = getattr(openai_module, "OpenAI", None)
    if client_cls is None:
        raise RuntimeError("Unsupported openai package: `OpenAI` client class not found.")

    kwargs: dict[str, Any] = {"api_key": config.api_key}
    if config.base_url:
        kwargs["base_url"] = config.base_url
    return client_cls(**kwargs)


def complete_messages(
    messages: list[Message], *, model: str | None = None, temperature: float = 0.0
) -> str:
    """Send exact message list to chat completions and return the text output."""
    config = load_config()
    client = _build_openai_client(config)
    target_model = model or config.model

    for attempt in range(len(_RETRY_DELAYS_SECONDS) + 1):
        try:
            # Demos require deterministic decoding so PASS/FAIL results are reproducible.
            response = client.chat.completions.create(
                model=target_model,
                messages=messages,
                temperature=0,
                top_p=1,
            )
            break
        except Exception as exc:
            exc_text = str(exc).lower()
            exc_name = exc.__class__.__name__.lower()
            if _is_model_not_found(exc_text, exc_name):
                raise DemoLLMError(
                    f"Model '{target_model}' was not found at the configured endpoint. "
                    "Check MODEL or OPENAI_BASE_URL."
                ) from exc
            if _is_authentication_error(exc_text, exc_name):
                raise DemoLLMError("Authentication failed. Check OPENAI_API_KEY.") from exc
            if _is_permission_error(exc_text, exc_name):
                raise DemoLLMError(
                    f"Access to model '{target_model}' was denied by the configured provider."
                ) from exc

            is_rate_limit = _is_rate_limit_error(exc_text, exc_name)
            is_timeout = _is_timeout_error(exc_text, exc_name)
            is_connection = _is_connection_error(exc_text, exc_name)

            if is_rate_limit or is_timeout or is_connection:
                retry_after = _retry_after_seconds(exc) if is_rate_limit else None
                if retry_after is None and is_rate_limit:
                    retry_after = _retry_after_seconds_from_text(str(exc))
                if retry_after is not None and retry_after > MAX_DEMO_RETRY_AFTER_SECONDS:
                    raise DemoLLMError(
                        f"LLM provider requested retry after {retry_after}s, "
                        "which exceeds the demo retry limit. "
                        "Try again later or switch providers."
                    ) from exc
                if attempt < len(_RETRY_DELAYS_SECONDS):
                    delay = (
                        retry_after if retry_after is not None else _RETRY_DELAYS_SECONDS[attempt]
                    )
                    if is_rate_limit:
                        print(
                            f"[retry] LLM rate limit hit — retrying in {delay}s...",
                            file=sys.stderr,
                        )
                    elif is_timeout:
                        print(
                            f"[retry] LLM timeout — retrying in {delay}s...",
                            file=sys.stderr,
                        )
                    else:
                        print(
                            f"[retry] LLM connection error — retrying in {delay}s...",
                            file=sys.stderr,
                        )
                    time.sleep(delay)
                    continue
                if is_rate_limit:
                    raise DemoLLMError(
                        "LLM provider rate limit exceeded. Try again later or switch providers."
                    ) from exc
                raise DemoLLMError(
                    "Could not reach the configured LLM endpoint after retries. "
                    "Check OPENAI_BASE_URL and network access."
                ) from exc

            raise DemoLLMError(
                f"LLM provider error while calling model '{target_model}': {exc}"
            ) from exc
    content = response.choices[0].message.content
    if isinstance(content, str):
        return content.strip()
    if content is None:
        return ""
    return str(content)
