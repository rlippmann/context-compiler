"""
title: Context Compiler Preprocessor Pipe
author: rlippmann
author_url: https://github.com/rlippmann/context-compiler
funding_url: https://github.com/rlippmann/context-compiler
version: 0.2
requirements: context-compiler[experimental]>=0.6.7

Open WebUI integration with Context Compiler preprocessor.

This example extends `open_webui_pipe.py` by inserting a preprocessing step:

1. Run heuristic precompiler (fast, high-precision cases)
2. Fall back to Open WebUI-native model completion when needed
3. Pass resulting directive (or original input) to `engine.step(...)`

Core decision handling remains the same as the base integration.
"""

import logging
from importlib.resources import as_file, files
from importlib.resources.abc import Traversable
from typing import Any, Literal

from fastapi import Request  # type: ignore[import-not-found]
from open_webui.models.users import Users  # type: ignore[import-not-found]
from open_webui.utils.chat import generate_chat_completion  # type: ignore[import-not-found]
from open_webui.utils.models import get_all_models  # type: ignore[import-not-found]

try:
    from pydantic import BaseModel, Field
except ModuleNotFoundError:
    # Keep this import optional: CI/tests run without integration extras.
    # These lightweight fallbacks keep import-time behavior deterministic so
    # coverage exercises the pipe module without pydantic installed.
    class BaseModel:  # type: ignore[no-redef]
        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    def Field(*, default: Any, description: str = "") -> Any:  # type: ignore[no-redef]
        del description
        return default


from context_compiler import State, create_engine, get_policy_items, get_premise_value
from context_compiler.engine import Engine
from experimental.preprocessor import (
    PRECOMPILE_OUTCOME_DIRECTIVE,
    parse_precompiler_output,
    precompile_heuristic,
    render_prompt,
)

logger = logging.getLogger(__name__)

_CC_MARKER = "[[cc_state]]"
_ENGINES_BY_CHAT_KEY: dict[str, Engine] = {}
# Example-only in-memory checkpoint store.
# This keeps continuation state only for the current process lifetime.
# Real deployments should persist checkpoints externally (DB/Redis/etc.),
# or restart continuity for pending flows will be lost.
_CHECKPOINTS_BY_CHAT_KEY: dict[str, str] = {}
_PROMPTS_DIR = files("experimental.preprocessor").joinpath("prompts")


def _prompt_file_path(profile: str) -> Traversable:
    # Runtime prompt selection for fallback precompilation:
    # - default: most instruction-following models
    # - llama: models that need tighter prompt guidance
    if profile == "llama":
        return _PROMPTS_DIR.joinpath("llama.txt")
    return _PROMPTS_DIR.joinpath("default.txt")


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


def _has_pending_clarification(engine: Engine) -> bool:
    return engine.export_checkpoint()["pending"] is not None


def _extract_completion_content(response: object) -> str | None:
    choices_attr = getattr(response, "choices", None)
    if isinstance(choices_attr, list) and choices_attr:
        first_choice = choices_attr[0]
        message_attr = getattr(first_choice, "message", None)
        content_attr = getattr(message_attr, "content", None)
        if isinstance(content_attr, str):
            return content_attr

    if isinstance(response, dict):
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                message = first_choice.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content

    return None


class Pipe:
    """Map Context Compiler decisions into Open WebUI pipe behavior.

    This variant adds a precompiler stage before ``engine.step(...)``:
    heuristic first, then Open WebUI-native LLM fallback.
    """

    class Valves(BaseModel):
        BASE_MODEL_ID: str = Field(
            default="",
            description="Open WebUI model id used as the base model for forwarding.",
        )
        PREPROCESSOR_MODEL_ID: str = Field(
            default="",
            description=(
                "Optional model id for fallback precompilation (defaults to BASE_MODEL_ID)."
            ),
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

    def _normalize_preprocessor_error(self, response: Any) -> str | None:
        if self._contains_model_not_found(response):
            return (
                "Context Compiler pipe misconfigured: PREPROCESSOR_MODEL_ID was not found "
                "in Open WebUI models."
            )
        return None

    def _normalize_preprocessor_exception(self, exc: Exception) -> str | None:
        detail = getattr(exc, "detail", None)
        if self._contains_model_not_found(detail) or self._contains_model_not_found(str(exc)):
            return (
                "Context Compiler pipe misconfigured: PREPROCESSOR_MODEL_ID was not found "
                "in Open WebUI models."
            )
        return None

    def _resolve_preprocessor_model_id(self, base_model_id: str) -> str:
        preprocessor_model_id = self.valves.PREPROCESSOR_MODEL_ID.strip()
        if preprocessor_model_id:
            return preprocessor_model_id
        return base_model_id

    async def _validate_configured_model_ids(
        self,
        request: Request,
        user_payload: dict[str, Any],
        *,
        base_model_id: str,
        preprocessor_model_id: str,
    ) -> str | None:
        # Best-effort preflight: fail closed only for clear missing-model mismatches.
        # If model discovery fails, preserve runtime behavior and rely on call-path
        # normalization below.
        user = Users.get_user_by_id(user_payload["id"])
        try:
            models = await get_all_models(request, user=user)
        except Exception:
            return None

        known_model_ids: set[str] = set()
        if isinstance(models, list):
            for model in models:
                if not isinstance(model, dict):
                    continue
                model_id = model.get("id")
                if isinstance(model_id, str):
                    known_model_ids.add(model_id)

        if base_model_id and base_model_id not in known_model_ids:
            return (
                "Context Compiler pipe misconfigured: BASE_MODEL_ID was not found "
                "in Open WebUI models."
            )
        if preprocessor_model_id and preprocessor_model_id not in known_model_ids:
            return (
                "Context Compiler pipe misconfigured: PREPROCESSOR_MODEL_ID was not found "
                "in Open WebUI models."
            )
        return None

    async def _llm_fallback_precompile(
        self,
        message: str,
        state: State,
        *,
        request: Request,
        user_payload: dict[str, Any],
        prompt_profile: str,
        model_id: str,
    ) -> tuple[str | None, str | None]:
        with as_file(_prompt_file_path(prompt_profile)) as prompt_path:
            prompt = render_prompt(prompt_path, state)
        if prompt is None:
            return None, None

        payload: dict[str, Any] = {
            "model": model_id,
            "stream": False,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": message},
            ],
        }
        user = Users.get_user_by_id(user_payload["id"])
        try:
            response = await generate_chat_completion(request, payload, user)
        except Exception as exc:
            normalized_exception = self._normalize_preprocessor_exception(exc)
            if normalized_exception is not None:
                return None, normalized_exception
            return None, None

        normalized_error = self._normalize_preprocessor_error(response)
        if normalized_error is not None:
            return None, normalized_error

        raw_output = _extract_completion_content(response)
        parsed = parse_precompiler_output(raw_output, source_input=message)
        if parsed is None:
            return None, None
        return parsed, None

    async def _precompile_user_input(
        self,
        message: str,
        state: State,
        *,
        request: Request,
        user_payload: dict[str, Any],
        prompt_profile: str,
        model_id: str,
    ) -> tuple[str | None, str | None]:
        # Heuristic first for precision, determinism, and low latency.
        # If heuristic does not produce a directive, try Open WebUI-native fallback.
        heuristic_result = precompile_heuristic(message)

        if (
            heuristic_result["outcome"] == PRECOMPILE_OUTCOME_DIRECTIVE
            and heuristic_result["directive"]
        ):
            parsed = parse_precompiler_output(heuristic_result["directive"])
            if parsed is not None:
                return parsed, None

        return await self._llm_fallback_precompile(
            message,
            state,
            request=request,
            user_payload=user_payload,
            prompt_profile=prompt_profile,
            model_id=model_id,
        )

    async def _forward_passthrough(
        self,
        body: dict[str, Any],
        user_payload: dict[str, Any],
        request: Request,
        *,
        base_model_id: str,
    ) -> Any:
        payload = {**body}
        payload["model"] = base_model_id
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
        *,
        base_model_id: str,
    ) -> Any:
        payload = {**body}
        payload["model"] = base_model_id

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
        preprocessor_model_id = self._resolve_preprocessor_model_id(base_model_id)
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
        if preprocessor_model_id and current_model_id and preprocessor_model_id == current_model_id:
            return (
                "Context Compiler pipe misconfigured: PREPROCESSOR_MODEL_ID must not "
                "match the selected pipe model id to avoid recursive routing."
            )

        preflight_error = await self._validate_configured_model_ids(
            __request__,
            __user__,
            base_model_id=base_model_id,
            preprocessor_model_id=preprocessor_model_id,
        )
        if preflight_error is not None:
            return preflight_error

        latest_user_text = _extract_latest_user_text(messages)
        logger.debug("preprocessor: user_input_found=%s", latest_user_text is not None)

        if latest_user_text is None:
            return await self._forward_passthrough(
                body,
                __user__,
                __request__,
                base_model_id=base_model_id,
            )

        chat_key = _resolve_chat_key(__user__, __chat_id__, __metadata__)
        engine = _ENGINES_BY_CHAT_KEY.get(chat_key)
        if engine is None:
            engine = create_engine()
            checkpoint = _CHECKPOINTS_BY_CHAT_KEY.get(chat_key)
            if checkpoint is not None:
                engine.import_checkpoint_json(checkpoint)
            _ENGINES_BY_CHAT_KEY[chat_key] = engine

        precompiled: str | None = None
        precompile_error: str | None = None
        if not _has_pending_clarification(engine):
            precompiled, precompile_error = await self._precompile_user_input(
                latest_user_text,
                engine.state,
                request=__request__,
                user_payload=__user__,
                prompt_profile=self.valves.PREPROCESSOR_PROMPT_PROFILE,
                model_id=preprocessor_model_id,
            )
            if precompile_error is not None:
                return precompile_error

        logger.debug("preprocessor: precompiled=%r", precompiled)
        # Preserve core behavior: if precompile yields no directive, use raw user
        # text so the compiler still decides clarify/passthrough/update.
        compile_input = precompiled if precompiled is not None else latest_user_text

        logger.debug("preprocessor: engine_input=%r", compile_input)
        decision = engine.step(compile_input)
        kind = decision["kind"]
        logger.debug("preprocessor: decision=%s", kind)

        if kind == "clarify":
            _CHECKPOINTS_BY_CHAT_KEY[chat_key] = engine.export_checkpoint_json()
            return decision["prompt_to_user"] or ""
        if kind == "passthrough":
            return await self._forward_passthrough(
                body,
                __user__,
                __request__,
                base_model_id=base_model_id,
            )
        if kind == "update":
            _CHECKPOINTS_BY_CHAT_KEY[chat_key] = engine.export_checkpoint_json()
            return await self._forward_update(
                body,
                __user__,
                __request__,
                engine.state,
                base_model_id=base_model_id,
            )

        return await self._forward_passthrough(
            body,
            __user__,
            __request__,
            base_model_id=base_model_id,
        )
