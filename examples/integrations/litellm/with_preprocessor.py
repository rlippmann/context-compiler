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
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TypedDict, cast

from context_compiler import State, get_policy_items, get_premise_value
from context_compiler.engine import Engine
from experimental.preprocessor.heuristic_precompiler import precompile_heuristic
from experimental.preprocessor.prompt_utils import render_prompt

logger = logging.getLogger(__name__)

_ALLOWED_DIRECTIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^set premise (?!to\b)\S(?:.*\S)?$"),
    re.compile(r"^change premise to \S(?:.*\S)?$"),
    re.compile(r"^use \S(?:.*\S)? instead of \S(?:.*\S)?$"),
    re.compile(r"^use (?!.*\sinstead of(?:\s|$))\S(?:.*\S)?$"),
    re.compile(r"^prohibit \S(?:.*\S)?$"),
    re.compile(r"^remove policy \S(?:.*\S)?$"),
)
_ALLOWED_DIRECTIVE_EXACT = {"clear premise", "reset policies", "clear state"}

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PROMPTS_DIR = _REPO_ROOT / "experimental" / "preprocessor" / "prompts"


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
    from litellm import completion  # type: ignore[import-not-found]

    return cast(Callable[..., object], completion)


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

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required.")

    kwargs: _LiteLLMCallKwargs = {
        "model": os.getenv("MODEL", "openai/gpt-4o-mini"),
        "messages": messages,
        "api_key": api_key,
        "temperature": 0,
    }
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        kwargs["api_base"] = base_url

    response = completion(**kwargs)
    content = _extract_response_content(response)
    if content is None:
        raise RuntimeError("LiteLLM response missing choices[0].message.content")
    return content


def _normalize_precompiler_output(raw_output: object) -> str | None:
    if not isinstance(raw_output, str):
        return None
    stripped = raw_output.strip()
    if stripped.upper() == "<NO_DIRECTIVE>":
        return "<NO_DIRECTIVE>"

    non_empty_lines = [line.strip() for line in raw_output.splitlines() if line.strip()]
    if non_empty_lines and non_empty_lines[-1].upper() == "<NO_DIRECTIVE>":
        return "<NO_DIRECTIVE>"

    return stripped


def _is_allowed_directive(text: str) -> bool:
    if text in _ALLOWED_DIRECTIVE_EXACT:
        return True
    return any(pattern.fullmatch(text) for pattern in _ALLOWED_DIRECTIVE_PATTERNS)


def _prompt_file_path() -> Path:
    profile = os.getenv("PREPROCESSOR_PROMPT_PROFILE", "default").strip().lower()
    if profile == "llama":
        return _PROMPTS_DIR / "llama.txt"
    return _PROMPTS_DIR / "default.txt"


def _llm_fallback_precompile(message: str, state: State) -> str | None:
    prompt = render_prompt(_prompt_file_path(), state)
    if prompt is None:
        return None

    try:
        completion = _get_litellm_completion()
    except ModuleNotFoundError:
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    kwargs: _LiteLLMCallKwargs = {
        "model": os.getenv("MODEL", "openai/gpt-4o-mini"),
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": message},
        ],
        "api_key": api_key,
        "temperature": 0,
    }
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        kwargs["api_base"] = base_url

    try:
        response = completion(**kwargs)
        raw_output = _extract_response_content(response)
    except Exception:
        return None

    parsed = _normalize_precompiler_output(raw_output)
    if parsed is None or parsed == "<NO_DIRECTIVE>" or not parsed:
        return None
    if not _is_allowed_directive(parsed):
        return None
    return parsed


def _precompile_user_input(message: str, state: State) -> str | None:
    # Heuristic first (fast + high precision), then optional LLM fallback.
    try:
        heuristic_result = precompile_heuristic(message)
        logger.debug("preprocessor: heuristic_outcome=%s", heuristic_result["outcome"])
        if heuristic_result["outcome"] == "directive" and heuristic_result["directive"]:
            logger.debug("preprocessor: heuristic_directive=%r", heuristic_result["directive"])
            return heuristic_result["directive"]
    except Exception:
        logger.debug("preprocessor: heuristic_exception", exc_info=True)

    try:
        fallback_directive = _llm_fallback_precompile(message, state)
        logger.debug("preprocessor: fallback_directive=%r", fallback_directive)
        return fallback_directive
    except Exception:
        # Safe no-op fallback: if preprocessor path fails, preserve basic behavior.
        return None


def handle_turn(user_input: str, engine: Engine) -> str:
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
        return decision["prompt_to_user"] or ""

    compiled_state = decision["state"] if decision["state"] is not None else engine.state
    messages = _build_messages(user_input, compiled_state)
    return _call_litellm(messages)
