"""Shared provider mode resolution for examples and demos."""

import logging
import os
from dataclasses import dataclass
from typing import Literal, cast

_ALLOWED_PROVIDER_VALUES = ("openai", "ollama", "openai_compatible")
_STARTUP_LOGGED = False


@dataclass(frozen=True)
class ProviderConfig:
    mode: Literal["openai", "ollama", "openai_compatible"]
    source: Literal["default", "PROVIDER", "OPENAI_BASE_URL override"]
    base_url: str
    model: str
    api_key: str | None


def resolve_provider_config(default_model: str = "openai/gpt-4o-mini") -> ProviderConfig:
    """Resolve provider mode config from environment using strict contract."""
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
    provider = os.getenv("PROVIDER", "").strip().lower() or None
    api_key = os.getenv("OPENAI_API_KEY", "").strip() or None
    model = os.getenv("MODEL", "").strip() or default_model

    if base_url:
        return ProviderConfig(
            mode="openai_compatible",
            source="OPENAI_BASE_URL override",
            base_url=base_url,
            model=model,
            api_key=api_key,
        )

    if provider is not None and provider not in _ALLOWED_PROVIDER_VALUES:
        allowed_values = ", ".join(_ALLOWED_PROVIDER_VALUES)
        raise RuntimeError(f"Invalid PROVIDER value '{provider}'. Allowed values: {allowed_values}")

    mode: Literal["openai", "ollama", "openai_compatible"]
    source: Literal["default", "PROVIDER", "OPENAI_BASE_URL override"]
    if provider is None:
        mode = "openai"
        source = "default"
    else:
        mode = cast(Literal["openai", "ollama", "openai_compatible"], provider)
        source = "PROVIDER"

    if mode == "openai":
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required in openai mode.")
        return ProviderConfig(
            mode=mode,
            source=source,
            base_url="https://api.openai.com/v1",
            model=model,
            api_key=api_key,
        )
    if mode == "ollama":
        return ProviderConfig(
            mode=mode,
            source=source,
            base_url="http://localhost:11434",
            model=model,
            api_key=api_key,
        )

    raise RuntimeError("OPENAI_BASE_URL is required when PROVIDER=openai_compatible.")


def print_startup_config(config: ProviderConfig, logger: logging.Logger | None = None) -> None:
    """Emit one startup line per process with resolved provider config."""
    global _STARTUP_LOGGED
    if _STARTUP_LOGGED:
        return
    target_logger = logger or logging.getLogger(__name__)
    target_logger.info(
        "litellm_config mode=%s base_url=%s model=%s source=%s",
        config.mode,
        config.base_url,
        config.model,
        config.source,
    )
    _STARTUP_LOGGED = True
