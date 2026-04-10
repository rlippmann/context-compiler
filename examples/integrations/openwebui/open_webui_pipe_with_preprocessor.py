"""
title: Context Compiler Preprocessor Pipe
author: rlippmann
author_url: https://github.com/rlippmann/context-compiler
funding_url: https://github.com/rlippmann/context-compiler
version: 0.1

Open WebUI integration with Context Compiler preprocessor.

This example extends `open_webui_pipe.py` by inserting a preprocessing step:

1. Run heuristic precompiler (fast, high-precision cases)
2. Fall back to LLM-based precompiler when needed
3. Pass resulting directive (or original input) to `engine.step(...)`

Core decision handling remains the same as the base integration.
"""

import importlib
import importlib.util
import logging
import os
import re
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

from fastapi import Request  # type: ignore[import-not-found]
from open_webui.models.users import Users  # type: ignore[import-not-found]
from open_webui.utils.chat import generate_chat_completion  # type: ignore[import-not-found]
from pydantic import BaseModel, Field

import context_compiler
from context_compiler import State, create_engine, get_policy_items, get_premise_value
from context_compiler.engine import Engine

logger = logging.getLogger(__name__)

_CC_MARKER = "[[cc_state]]"
_ENGINES_BY_CHAT_KEY: dict[str, Engine] = {}
_HEURISTIC_PRECOMPILE: Any | None = None
_RENDER_PROMPT_HELPER: Any | None = None

# Keep accepted output strict: fallback text must be a canonical directive line
# or we treat it as no directive.
_ALLOWED_DIRECTIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^set premise (?!to\b)\S(?:.*\S)?$"),
    re.compile(r"^change premise to \S(?:.*\S)?$"),
    re.compile(r"^use \S(?:.*\S)? instead of \S(?:.*\S)?$"),
    re.compile(r"^use (?!.*\sinstead of(?:\s|$))\S(?:.*\S)?$"),
    re.compile(r"^prohibit \S(?:.*\S)?$"),
    re.compile(r"^remove policy \S(?:.*\S)?$"),
)
_ALLOWED_DIRECTIVE_EXACT = {"clear premise", "reset policies", "clear state"}


class PrecompileResult(TypedDict):
    outcome: Literal["directive", "no_directive", "unknown"]
    directive: str | None
    rule_id: str | None


_NOOP_PRECOMPILE_RESULT: PrecompileResult = {
    "outcome": "no_directive",
    "directive": None,
    "rule_id": "unavailable",
}


def _noop_precompile(_message: str) -> PrecompileResult:
    return _NOOP_PRECOMPILE_RESULT


def _repo_root() -> Path:
    env_root = os.getenv("CONTEXT_COMPILER_REPO_ROOT", "").strip()
    candidates: list[Path] = []

    if env_root:
        candidates.append(Path(env_root))

    cwd = Path.cwd()
    candidates.extend([cwd, *cwd.parents])

    package_root_candidates = [Path(context_compiler.__file__).resolve().parent]
    for package_root in package_root_candidates:
        candidates.extend([package_root, *package_root.parents])

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        heuristic_path = resolved / "experimental" / "preprocessor" / "heuristic_precompiler.py"
        if heuristic_path.exists():
            return resolved

    raise RuntimeError(
        "Unable to locate context-compiler repo root. "
        "Set CONTEXT_COMPILER_REPO_ROOT to a checkout path that contains "
        "experimental/preprocessor/heuristic_precompiler.py."
    )


def _prompt_file_path(profile: str) -> Path:
    # Runtime prompt selection for fallback precompilation:
    # - default: most instruction-following models
    # - llama: models that need tighter prompt guidance
    prompts_dir = _repo_root() / "experimental" / "preprocessor" / "prompts"
    if profile == "llama":
        return prompts_dir / "llama.txt"
    return prompts_dir / "default.txt"


def _load_heuristic_precompile() -> Any:
    module_path = _repo_root() / "experimental" / "preprocessor" / "heuristic_precompiler.py"
    spec = importlib.util.spec_from_file_location("heuristic_precompiler_runtime", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load heuristic precompiler module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, "precompile_heuristic", None)
    if fn is None or not callable(fn):
        raise RuntimeError("heuristic_precompiler.py does not define callable precompile_heuristic")
    return fn


def _load_render_prompt_helper() -> Any:
    """Load shared prompt renderer from experimental preprocessor utilities."""
    module_path = _repo_root() / "experimental" / "preprocessor" / "prompt_utils.py"
    spec = importlib.util.spec_from_file_location("preprocessor_prompt_utils_runtime", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load prompt utils module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, "render_prompt", None)
    if fn is None or not callable(fn):
        raise RuntimeError("prompt_utils.py does not define callable render_prompt")
    return fn


def _get_heuristic_precompile() -> Any:
    # Load once per process to keep per-message overhead low in this example.
    global _HEURISTIC_PRECOMPILE
    if _HEURISTIC_PRECOMPILE is None:
        try:
            _HEURISTIC_PRECOMPILE = _load_heuristic_precompile()
        except Exception as exc:
            logger.debug("preprocessor: heuristic_unavailable=%s", exc)
            _HEURISTIC_PRECOMPILE = _noop_precompile
    return _HEURISTIC_PRECOMPILE


def _get_render_prompt_helper() -> Any:
    """Return cached render helper; return ``None`` when unavailable."""
    global _RENDER_PROMPT_HELPER
    if _RENDER_PROMPT_HELPER is None:
        try:
            _RENDER_PROMPT_HELPER = _load_render_prompt_helper()
        except Exception as exc:
            logger.debug("preprocessor: prompt_render_helper_unavailable=%s", exc)
            _RENDER_PROMPT_HELPER = None
    return _RENDER_PROMPT_HELPER


def _resolve_chat_key(
    user: dict[str, Any],
    chat_id: str | None,
    metadata: dict[str, Any] | None,
) -> str:
    if chat_id:
        return chat_id
    if isinstance(metadata, dict):
        metadata_chat_id = metadata.get("chat_id")
        if isinstance(metadata_chat_id, str) and metadata_chat_id:
            return metadata_chat_id
    user_id = str(user["id"])
    return f"no-chat-id:{user_id}"


def _extract_latest_user_text(messages: list[dict[str, Any]]) -> str | None:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        return None
    return None


def _render_compiler_state_block(state: State) -> str:
    lines: list[str] = [_CC_MARKER]

    premise = get_premise_value(state)
    if premise is not None:
        lines.append(f"Premise: {premise}")

    use_items = sorted(get_policy_items(state, "use"))
    if use_items:
        lines.append("Use: " + ", ".join(use_items))

    prohibit_items = sorted(get_policy_items(state, "prohibit"))
    if prohibit_items:
        lines.append("Prohibit: " + ", ".join(prohibit_items))

    return "\n".join(lines)


def _replace_compiler_system_message(
    messages: list[dict[str, Any]],
    rendered_state_block: str,
) -> list[dict[str, Any]]:
    filtered_messages: list[dict[str, Any]] = []
    last_system_index = -1

    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role == "system" and isinstance(content, str) and content.startswith(_CC_MARKER):
            continue

        filtered_messages.append(message)
        if role == "system":
            last_system_index = len(filtered_messages) - 1

    insert_at = last_system_index + 1 if last_system_index >= 0 else 0
    compiler_message: dict[str, Any] = {"role": "system", "content": rendered_state_block}
    return [
        *filtered_messages[:insert_at],
        compiler_message,
        *filtered_messages[insert_at:],
    ]


def _normalize_precompiler_output(raw_output: object) -> str | None:
    # Fallback responses can be malformed or non-text depending on provider/model.
    # Treat invalid content as no directive rather than failing request handling.
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


def _llm_fallback_precompile(
    message: str, state: State, *, prompt_profile: str, model: str
) -> str | None:
    # Fallback is optional. If prompt files, dependencies, or credentials are
    # unavailable, we return no directive and continue normal compiler flow.
    try:
        prompt_path = _prompt_file_path(prompt_profile)
    except Exception as exc:
        logger.debug("preprocessor: prompt_unavailable=%s", exc)
        return None
    render_prompt = _get_render_prompt_helper()
    if render_prompt is None:
        return None
    prompt = cast(str | None, render_prompt(prompt_path, state))
    if prompt is None:
        return None

    try:
        litellm_module = importlib.import_module("litellm")
        completion = cast(Any, litellm_module.completion)
    except ModuleNotFoundError:
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": message},
        ],
        "api_key": api_key,
        "temperature": 0,
    }
    api_base = os.getenv("OPENAI_BASE_URL")
    if api_base:
        kwargs["api_base"] = api_base

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


def _precompile_user_input(
    message: str,
    state: State,
    *,
    prompt_profile: str,
    model: str,
) -> str | None:
    # Heuristic first for precision, determinism, and low latency.
    # If heuristic does not produce a directive, try LLM fallback.
    heuristic = _get_heuristic_precompile()
    heuristic_result = cast(PrecompileResult, heuristic(message))

    if heuristic_result["outcome"] == "directive" and heuristic_result["directive"]:
        return heuristic_result["directive"]

    return _llm_fallback_precompile(
        message,
        state,
        prompt_profile=prompt_profile,
        model=model,
    )


class Pipe:
    """Map Context Compiler decisions into Open WebUI pipe behavior.

    This variant adds a precompiler stage before ``engine.step(...)``:
    heuristic first, then LLM fallback.
    """

    class Valves(BaseModel):
        BASE_MODEL_ID: str = Field(
            default="",
            description="Open WebUI model id used as the base model for forwarding.",
        )
        PREPROCESSOR_PROMPT_PROFILE: Literal["default", "llama"] = Field(
            default="default",
            description="Prompt profile for LLM fallback precompilation.",
        )
        ALLOW_MISSING_BASE_MODEL_FOR_DEBUG: bool = Field(
            default=False,
            description="Allow missing BASE_MODEL_ID for debug/testing only.",
        )

    def __init__(self) -> None:
        self.valves = self.Valves()

    def _is_model_not_found_text(self, value: object) -> bool:
        if not isinstance(value, str):
            return False
        return "model not found" in value.lower()

    def _contains_model_not_found(self, value: object) -> bool:
        if self._is_model_not_found_text(value):
            return True
        if isinstance(value, dict):
            return any(self._contains_model_not_found(v) for v in value.values())
        if isinstance(value, list):
            return any(self._contains_model_not_found(v) for v in value)
        return False

    def _normalize_forward_error(self, response: Any) -> str | None:
        if self._contains_model_not_found(response):
            return (
                "Context Compiler pipe misconfigured: BASE_MODEL_ID was not found "
                "in Open WebUI models."
            )
        return None

    def _normalize_forward_exception(self, exc: Exception) -> str | None:
        detail = getattr(exc, "detail", None)
        if self._contains_model_not_found(detail) or self._contains_model_not_found(str(exc)):
            return (
                "Context Compiler pipe misconfigured: BASE_MODEL_ID was not found "
                "in Open WebUI models."
            )
        return None

    async def _forward_passthrough(
        self,
        body: dict[str, Any],
        user_payload: dict[str, Any],
        request: Request,
    ) -> Any:
        payload = {**body}
        payload["model"] = self.valves.BASE_MODEL_ID
        user = Users.get_user_by_id(user_payload["id"])
        try:
            response = await generate_chat_completion(request, payload, user)
        except Exception as exc:
            normalized_exception = self._normalize_forward_exception(exc)
            if normalized_exception is not None:
                return normalized_exception
            raise
        normalized_error = self._normalize_forward_error(response)
        if normalized_error is not None:
            return normalized_error
        return response

    async def _forward_update(
        self,
        body: dict[str, Any],
        user_payload: dict[str, Any],
        request: Request,
        state: State,
    ) -> Any:
        payload = {**body}
        payload["model"] = self.valves.BASE_MODEL_ID

        raw_messages = body.get("messages")
        messages = (
            [dict(msg) for msg in raw_messages if isinstance(msg, dict)]
            if isinstance(raw_messages, list)
            else []
        )
        payload["messages"] = _replace_compiler_system_message(
            messages,
            _render_compiler_state_block(state),
        )

        user = Users.get_user_by_id(user_payload["id"])
        try:
            response = await generate_chat_completion(request, payload, user)
        except Exception as exc:
            normalized_exception = self._normalize_forward_exception(exc)
            if normalized_exception is not None:
                return normalized_exception
            raise
        normalized_error = self._normalize_forward_error(response)
        if normalized_error is not None:
            return normalized_error
        return response

    async def pipe(
        self,
        body: dict[str, Any],
        __user__: dict[str, Any],
        __request__: Request,
        __chat_id__: str | None = None,
        __metadata__: dict[str, Any] | None = None,
    ) -> Any:
        # Open WebUI integration entrypoint:
        # 1) extract latest user input
        # 2) run precompile (heuristic -> LLM fallback)
        # 3) pass directive or original input to engine.step(...)
        # 4) map decision back to Open WebUI response behavior
        raw_messages = body.get("messages")
        messages = (
            [msg for msg in raw_messages if isinstance(msg, dict)]
            if isinstance(raw_messages, list)
            else []
        )
        base_model_id = self.valves.BASE_MODEL_ID.strip()
        current_model_id = str(body.get("model", "")).strip()
        if not base_model_id and not self.valves.ALLOW_MISSING_BASE_MODEL_FOR_DEBUG:
            return (
                "Context Compiler pipe misconfigured: BASE_MODEL_ID is required "
                "(or set ALLOW_MISSING_BASE_MODEL_FOR_DEBUG=true for testing)."
            )
        if base_model_id and current_model_id and base_model_id == current_model_id:
            return (
                "Context Compiler pipe misconfigured: BASE_MODEL_ID must not match "
                "the selected pipe model id to avoid recursive routing."
            )

        latest_user_text = _extract_latest_user_text(messages)
        logger.debug("preprocessor: user_input_found=%s", latest_user_text is not None)

        if latest_user_text is None:
            return await self._forward_passthrough(body, __user__, __request__)

        chat_key = _resolve_chat_key(__user__, __chat_id__, __metadata__)
        engine = _ENGINES_BY_CHAT_KEY.get(chat_key)
        if engine is None:
            engine = create_engine()
            _ENGINES_BY_CHAT_KEY[chat_key] = engine

        precompiled = _precompile_user_input(
            latest_user_text,
            engine.state,
            prompt_profile=self.valves.PREPROCESSOR_PROMPT_PROFILE,
            model=base_model_id,
        )
        logger.debug("preprocessor: precompiled=%r", precompiled)
        # Preserve core behavior: if precompile yields no directive, use raw user
        # text so the compiler still decides clarify/passthrough/update.
        compile_input = precompiled if precompiled is not None else latest_user_text

        logger.debug("preprocessor: engine_input=%r", compile_input)
        decision = engine.step(compile_input)
        kind = decision["kind"]
        logger.debug("preprocessor: decision=%s", kind)

        if kind == "clarify":
            return decision["prompt_to_user"] or ""
        if kind == "passthrough":
            return await self._forward_passthrough(body, __user__, __request__)
        if kind == "update":
            return await self._forward_update(body, __user__, __request__, engine.state)

        return await self._forward_passthrough(body, __user__, __request__)
