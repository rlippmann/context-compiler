"""
Open WebUI integration with Context Compiler preprocessor.

This example extends `open_webui_pipe.py` by inserting a preprocessing step:

1. Run heuristic precompiler (fast, high-precision cases)
2. Fall back to LLM-based precompiler when needed
3. Pass resulting directive (or original input) to `engine.step(...)`

Core decision handling remains the same as the base integration.
"""

import importlib.util
import logging
import os
import re
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

from fastapi import Request  # type: ignore[import-not-found]
from open_webui.models.users import Users  # type: ignore[import-not-found]
from open_webui.utils.chat import generate_chat_completion  # type: ignore[import-not-found]
from pydantic import BaseModel, Field  # type: ignore[import-not-found]

from context_compiler import State, create_engine, get_policy_items, get_premise_value
from context_compiler.engine import Engine

logger = logging.getLogger(__name__)

_CC_MARKER = "[[cc_state]]"
_ENGINES_BY_CHAT_KEY: dict[str, Engine] = {}
_HEURISTIC_PRECOMPILE: Any | None = None

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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


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


def _get_heuristic_precompile() -> Any:
    # Load once per process to keep per-message overhead low in this example.
    global _HEURISTIC_PRECOMPILE
    if _HEURISTIC_PRECOMPILE is None:
        _HEURISTIC_PRECOMPILE = _load_heuristic_precompile()
    return _HEURISTIC_PRECOMPILE


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


def _render_prompt_template(prompt_template: str, state: State) -> str:
    premise = get_premise_value(state)
    premise_value = "null" if premise is None else premise

    all_policy_items = sorted(
        set(get_policy_items(state, "use")) | set(get_policy_items(state, "prohibit"))
    )
    policies_value = ", ".join(all_policy_items) if all_policy_items else "(none)"

    rendered = prompt_template.replace("<NULL_OR_VALUE>", premise_value)
    rendered = rendered.replace("<SET OF CURRENT POLICY ITEMS>", policies_value)
    return rendered


def _llm_fallback_precompile(
    message: str, state: State, *, prompt_profile: str, model: str
) -> str | None:
    # Fallback is optional. If prompt files, dependencies, or credentials are
    # unavailable, we return no directive and continue normal compiler flow.
    prompt_path = _prompt_file_path(prompt_profile)
    if not prompt_path.exists():
        return None

    prompt_template = prompt_path.read_text(encoding="utf-8")
    prompt = _render_prompt_template(prompt_template, state)

    try:
        from litellm import completion  # type: ignore[import-not-found]
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
    message: str, state: State, *, prompt_profile: str, model: str
) -> str | None:
    # Heuristic first for precision, determinism, and low latency.
    # If heuristic does not produce a directive, try LLM fallback.
    heuristic = _get_heuristic_precompile()
    heuristic_result = cast(PrecompileResult, heuristic(message))

    if heuristic_result["outcome"] == "directive" and heuristic_result["directive"]:
        return heuristic_result["directive"]

    return _llm_fallback_precompile(message, state, prompt_profile=prompt_profile, model=model)


class Pipe:
    """Map Context Compiler decisions into Open WebUI pipe behavior.

    This variant adds a precompiler stage before ``engine.step(...)``:
    heuristic first, then LLM fallback.
    """

    class Valves(BaseModel):  # type: ignore[misc]
        BASE_MODEL_ID: str = Field(
            default="gpt-4o-mini",
            description="Open WebUI model id used as the base model for forwarding.",
        )
        PREPROCESSOR_MODEL_ID: str = Field(
            default="gpt-4.1-mini",
            description="Model id used for LLM fallback precompilation.",
        )
        PREPROCESSOR_PROMPT_PROFILE: Literal["default", "llama"] = Field(
            default="default",
            description="Prompt profile for LLM fallback precompilation.",
        )

    def __init__(self) -> None:
        self.valves = self.Valves()

    async def _forward_passthrough(
        self,
        body: dict[str, Any],
        user_payload: dict[str, Any],
        request: Request,
    ) -> Any:
        payload = {**body}
        payload["model"] = self.valves.BASE_MODEL_ID
        user = Users.get_user_by_id(user_payload["id"])
        return await generate_chat_completion(request, payload, user)

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
        return await generate_chat_completion(request, payload, user)

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
            model=self.valves.PREPROCESSOR_MODEL_ID,
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
