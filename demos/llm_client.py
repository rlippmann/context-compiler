"""Small OpenAI-compatible chat client for demo scripts."""

import os
from dataclasses import dataclass
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


def load_config() -> LLMConfig:
    """Load OpenAI-compatible configuration from environment variables."""
    base_url = os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY") or ("ollama" if base_url else "")
    model = os.getenv("MODEL", "gpt-4.1-mini")

    if not api_key:
        raise RuntimeError("Set OPENAI_API_KEY (or OPENAI_BASE_URL for local Ollama).")

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

    response = client.chat.completions.create(
        model=target_model,
        messages=messages,
        temperature=temperature,
    )
    content = response.choices[0].message.content
    if isinstance(content, str):
        return content.strip()
    if content is None:
        return ""
    return str(content)
