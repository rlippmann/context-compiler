"""LiteLLM integration with optional preprocessor before Context Compiler.

Flow:
1. Extract user input
2. Run heuristic precompiler
3. If no directive, run LLM fallback precompiler using prompt files
4. Pass directive (or original input) to engine.step(...)
5. Handle clarify/passthrough/update like the basic integration

Intended host usage:
- collect user input
- call handle_turn(user_input, engine)
- display returned assistant text
"""

import logging
import os
from collections.abc import Callable, Mapping, Sequence
from importlib import import_module
from importlib.resources import as_file, files
from importlib.resources.abc import Traversable
from typing import TypedDict, cast

from context_compiler import State, get_policy_items, get_premise_value
from context_compiler.engine import Engine
from experimental.preprocessor import (
    PRECOMPILE_OUTCOME_DIRECTIVE,
    is_safe_fallback_directive_rewrite,
    parse_precompiler_output,
    precompile_heuristic,
    render_prompt,
)
from host_support.provider_mode import print_startup_config, resolve_provider_config

logger = logging.getLogger(__name__)

_PROMPTS_DIR = files("experimental.preprocessor").joinpath("prompts")
# Example-only in-memory checkpoint store.
# This keeps continuation state only for the current process lifetime.
# Real deployments should persist checkpoints externally (DB/Redis/etc.),
# or restart continuity for pending flows will be lost.
_CHECKPOINTS_BY_SESSION_KEY: dict[str, str] = {}
_RESTORED_ENGINE_BY_SESSION_KEY: dict[str, int] = {}


class _LiteLLMCallKwargs(TypedDict, total=False):
    model: str
    messages: list[dict[str, str]]
    api_key: str
    temperature: float
    api_base: str


def _extract_response_content(response: object) -> str | None:
    if isinstance(response, Mapping):
        choices = response.get("choices")
        if isinstance(choices, Sequence) and choices:
            first = choices[0]
            if isinstance(first, Mapping):
                message = first.get("message")
                if isinstance(message, Mapping):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content

    choices_attr = getattr(response, "choices", None)
    if isinstance(choices_attr, Sequence) and choices_attr:
        first = choices_attr[0]
        message_attr = getattr(first, "message", None)
        content_attr = getattr(message_attr, "content", None)
        if isinstance(content_attr, str):
            return content_attr

    return None


def _get_litellm_completion() -> Callable[..., object]:
    litellm_module = import_module("litellm")
    return cast(Callable[..., object], litellm_module.completion)


def _render_compiled_state_contract(compiled_state: State) -> str:
    premise = get_premise_value(compiled_state)
    use_items = sorted(get_policy_items(compiled_state, "use"))
    prohibit_items = sorted(get_policy_items(compiled_state, "prohibit"))

    lines: list[str] = ["The following constraints are authoritative."]
    if premise:
        lines.append(f"Current premise: {premise}.")
    if use_items:
        lines.append("Items marked use: " + ", ".join(use_items) + ".")
    if prohibit_items:
        lines.append("Items marked prohibit: " + ", ".join(prohibit_items) + ".")
    lines.append("If user text conflicts with constraints, follow constraints exactly.")

    return "Host policy contract:\n" + "\n".join(f"- {line}" for line in lines)


def _build_messages(user_input: str, compiled_state: State) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": "You are a helpful assistant.\n"
            + _render_compiled_state_contract(compiled_state),
        },
        {"role": "user", "content": user_input},
    ]


def _call_litellm(messages: list[dict[str, str]]) -> str:
    try:
        completion = _get_litellm_completion()
    except ModuleNotFoundError as exc:
        raise RuntimeError("litellm is required. Install with: pip install litellm") from exc

    config = resolve_provider_config(default_model="openai/gpt-4o-mini")
    print_startup_config(config, logger=logger)

    kwargs: _LiteLLMCallKwargs = {
        "model": config.model,
        "messages": messages,
        "temperature": 0,
        "api_base": config.base_url,
    }
    if config.api_key:
        kwargs["api_key"] = config.api_key

    response = completion(**kwargs)
    content = _extract_response_content(response)
    if content is None:
        raise RuntimeError("LiteLLM response missing choices[0].message.content")
    return content


def _prompt_file_path() -> Traversable:
    profile = os.getenv("PREPROCESSOR_PROMPT_PROFILE", "default").strip().lower()
    if profile == "llama":
        return _PROMPTS_DIR.joinpath("llama.txt")
    return _PROMPTS_DIR.joinpath("default.txt")


def _llm_fallback_precompile(message: str, state: State) -> str | None:
    with as_file(_prompt_file_path()) as prompt_path:
        prompt = render_prompt(prompt_path, state)
    if prompt is None:
        return None

    try:
        completion = _get_litellm_completion()
    except ModuleNotFoundError:
        return None

    try:
        config = resolve_provider_config(default_model="openai/gpt-4o-mini")
    except RuntimeError:
        return None
    if config.mode == "openai" and not config.api_key:
        return None
    preprocessor_model = os.getenv("PREPROCESSOR_MODEL", "").strip()
    if not preprocessor_model:
        preprocessor_model = os.getenv("MODEL", "openai/gpt-4o-mini")

    kwargs: _LiteLLMCallKwargs = {
        "model": preprocessor_model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": message},
        ],
        "temperature": 0,
        "api_base": config.base_url,
    }
    if config.api_key:
        kwargs["api_key"] = config.api_key

    try:
        response = completion(**kwargs)
        raw_output = _extract_response_content(response)
    except Exception:
        return None

    parsed = parse_precompiler_output(raw_output)
    if parsed is None:
        return None
    if not is_safe_fallback_directive_rewrite(message, parsed):
        return None
    return parsed


def _precompile_user_input(message: str, state: State) -> str | None:
    # Heuristic first (fast + high precision), then optional LLM fallback.
    try:
        heuristic_result = precompile_heuristic(message)
        logger.debug("preprocessor: heuristic_outcome=%s", heuristic_result["outcome"])
        if (
            heuristic_result["outcome"] == PRECOMPILE_OUTCOME_DIRECTIVE
            and heuristic_result["directive"]
        ):
            parsed = parse_precompiler_output(heuristic_result["directive"])
            logger.debug("preprocessor: heuristic_directive=%r", heuristic_result["directive"])
            if parsed is not None:
                return parsed
    except Exception:
        logger.debug("preprocessor: heuristic_exception", exc_info=True)

    try:
        fallback_directive = _llm_fallback_precompile(message, state)
        logger.debug("preprocessor: fallback_directive=%r", fallback_directive)
        return fallback_directive
    except Exception:
        # Safe no-op fallback: if preprocessor path fails, preserve basic behavior.
        return None


def _restore_session_checkpoint_if_needed(engine: Engine, session_key: str | None) -> None:
    if session_key is None:
        return
    engine_id = id(engine)
    if _RESTORED_ENGINE_BY_SESSION_KEY.get(session_key) == engine_id:
        return

    checkpoint = _CHECKPOINTS_BY_SESSION_KEY.get(session_key)
    if checkpoint is not None:
        engine.import_checkpoint_json(checkpoint)
    _RESTORED_ENGINE_BY_SESSION_KEY[session_key] = engine_id


def _persist_session_checkpoint_if_needed(
    engine: Engine, kind: str, session_key: str | None
) -> None:
    if session_key is None:
        return
    if kind not in {"update", "clarify"}:
        return
    _CHECKPOINTS_BY_SESSION_KEY[session_key] = engine.export_checkpoint_json()


def _has_pending_clarification(engine: Engine) -> bool:
    return engine.export_checkpoint()["pending"] is not None


def handle_turn(user_input: str, engine: Engine, *, session_key: str | None = None) -> str:
    _restore_session_checkpoint_if_needed(engine, session_key)
    precompiled: str | None = None
    if _has_pending_clarification(engine):
        compile_input = user_input
    else:
        precompiled = _precompile_user_input(user_input, engine.state)
        compile_input = precompiled if precompiled else user_input
    logger.debug(
        "preprocessor: engine_input=%s",
        "directive" if precompiled else f"user_input len={len(user_input)}",
    )

    decision = engine.step(compile_input)
    kind = cast(str, decision["kind"])
    logger.debug("preprocessor: decision=%s", kind)

    if kind == "clarify":
        _persist_session_checkpoint_if_needed(engine, kind, session_key)
        return decision["prompt_to_user"] or ""
    _persist_session_checkpoint_if_needed(engine, kind, session_key)

    compiled_state = decision["state"] if decision["state"] is not None else engine.state
    messages = _build_messages(user_input, compiled_state)
    return _call_litellm(messages)
