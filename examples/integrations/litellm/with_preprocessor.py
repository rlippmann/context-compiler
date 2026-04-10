"""LiteLLM integration with optional preprocessor before Context Compiler.

Flow:
1. Extract user input
2. Run heuristic precompiler
3. If no directive, run LLM fallback precompiler using prompt files
4. Pass directive (or original input) to engine.step(...)
5. Handle clarify/passthrough/update like the basic integration
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, cast

from context_compiler import State, create_engine, get_policy_items, get_premise_value
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


def _get_litellm_completion() -> Any:
    from litellm import completion  # type: ignore[import-not-found]

    return completion


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

    kwargs: dict[str, Any] = {
        "model": os.getenv("MODEL", "openai/gpt-4o-mini"),
        "messages": messages,
        "api_key": api_key,
        "temperature": 0,
    }
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        kwargs["api_base"] = base_url

    response = completion(**kwargs)
    return cast(str, response["choices"][0]["message"]["content"])


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

    kwargs: dict[str, Any] = {
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
        raw_output = cast(Any, response.choices[0].message.content)
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
    except Exception:
        return None

    if heuristic_result["outcome"] == "directive" and heuristic_result["directive"]:
        return heuristic_result["directive"]

    try:
        return _llm_fallback_precompile(message, state)
    except Exception:
        # Safe no-op fallback: if preprocessor path fails, preserve basic behavior.
        return None


def handle_turn(user_input: str, engine: Any) -> str:
    precompiled = _precompile_user_input(user_input, cast(State, engine.state))
    logger.debug("preprocessor: precompiled=%r", precompiled)

    compile_input = precompiled if precompiled else user_input
    logger.debug("preprocessor: engine_input=%r", compile_input)

    decision = engine.step(compile_input)
    kind = cast(str, decision["kind"])
    logger.debug("preprocessor: decision=%s", kind)

    if kind == "clarify":
        return cast(str, decision["prompt_to_user"] or "")

    compiled_state = cast(
        State, decision["state"] if decision["state"] is not None else engine.state
    )
    messages = _build_messages(user_input, compiled_state)
    return _call_litellm(messages)


def main() -> None:
    engine = create_engine()

    turns = [
        "set premise to concise replies",
        "change premise to formal tone",
        "use docker",
        "prohibit docker",
        "use podman instead of docker",
        "please use docker",
        "I usually use docker",
    ]

    for turn in turns:
        print(f"User: {turn}")
        print(f"Assistant: {handle_turn(turn, engine)}")
        print()


if __name__ == "__main__":
    main()
