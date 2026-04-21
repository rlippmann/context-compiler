"""LiteLLM Proxy pre-call hook with optional preprocessor on latest user message.

Architecture:
- Replay user transcript through Context Compiler before any model call.
- Preprocess only the latest user message for compiler replay input.
- If clarification is required, block upstream model call.
- Otherwise inject compiled state guidance into a system message.
"""

import logging
import os
from collections.abc import Callable, Mapping, Sequence
from importlib import import_module
from importlib.resources import as_file, files
from importlib.resources.abc import Traversable
from typing import Any, cast

try:
    from litellm.integrations.custom_logger import CustomLogger
except ModuleNotFoundError:

    class CustomLogger:  # type: ignore[no-redef]
        pass


from context_compiler import (
    State,
    Transcript,
    compile_transcript,
    get_policy_items,
    get_premise_value,
)
from experimental.preprocessor import (
    PRECOMPILE_OUTCOME_DIRECTIVE,
    PRECOMPILER_NO_DIRECTIVE_SENTINEL,
    parse_precompiler_output,
    precompile_heuristic,
    render_prompt,
)

logger = logging.getLogger(__name__)

_SUPPORTED_CALL_TYPES = {
    "completion",
    "acompletion",
    "chat_completion",
    "achat_completion",
}

_PROMPTS_DIR = files("experimental.preprocessor").joinpath("prompts")


def _render_compiled_state_contract(compiled_state: State) -> str:
    prohibited = get_policy_items(compiled_state, "prohibit")
    premise = get_premise_value(compiled_state)

    lines: list[str] = ["The following constraints are authoritative."]
    if prohibited:
        items = ", ".join(prohibited)
        lines.append(f"Never recommend or use prohibited items: {items}.")
    if premise:
        lines.append(
            "When the answer depends on user preference/style, "
            f"treat the current premise as: {premise}."
        )
    lines.append("If the user message conflicts with these constraints, follow them exactly.")

    return "Host policy contract:\n" + "\n".join(f"- {line}" for line in lines)


def _extract_request_messages(data: dict[str, object]) -> list[dict[str, object]]:
    raw_messages = data.get("messages")
    if not isinstance(raw_messages, list):
        return []
    return [msg for msg in raw_messages if isinstance(msg, dict)]


def _extract_text_content(content: object) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "text":
                continue
            text = item.get("text")
            if isinstance(text, str):
                text_parts.append(text)
        if text_parts:
            return " ".join(text_parts)
    return None


def _extract_user_transcript(messages: list[dict[str, object]]) -> Transcript:
    transcript: Transcript = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        text_content = _extract_text_content(content)
        if role == "user" and text_content is not None:
            transcript.append({"role": "user", "content": text_content})
    return transcript


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


def _prompt_file_path() -> Traversable:
    profile = os.getenv("PREPROCESSOR_PROMPT_PROFILE", "default").strip().lower()
    if profile == "llama":
        return _PROMPTS_DIR.joinpath("llama.txt")
    return _PROMPTS_DIR.joinpath("default.txt")


def _get_litellm_completion() -> Callable[..., object]:
    litellm_module = import_module("litellm")
    return cast(Callable[..., object], litellm_module.completion)


def _llm_fallback_precompile(message: str, state: State) -> str | None:
    with as_file(_prompt_file_path()) as prompt_path:
        prompt = render_prompt(prompt_path, state)
    if prompt is None:
        return None

    preprocessor_model = os.getenv("PREPROCESSOR_MODEL", "").strip()
    if not preprocessor_model:
        preprocessor_model = os.getenv("MODEL", "").strip()
    if not preprocessor_model:
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        completion = _get_litellm_completion()
    except ModuleNotFoundError:
        return None

    kwargs: dict[str, object] = {
        "model": preprocessor_model,
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
        raw_output = _extract_response_content(response)
    except Exception:
        return None

    parsed = parse_precompiler_output(raw_output)
    if parsed is None or parsed == PRECOMPILER_NO_DIRECTIVE_SENTINEL:
        return None
    return parsed


def _state_before_last_message(user_transcript: Transcript) -> State | None:
    if not user_transcript:
        return None
    prefix = user_transcript[:-1]
    replay = compile_transcript(prefix)
    if replay["kind"] != "state":
        return None
    return replay["state"]


def _precompile_last_user_message(message: str, state: State | None) -> str | None:
    try:
        heuristic_result = precompile_heuristic(message)
        if (
            heuristic_result["outcome"] == PRECOMPILE_OUTCOME_DIRECTIVE
            and heuristic_result["directive"]
        ):
            parsed = parse_precompiler_output(heuristic_result["directive"])
            if parsed is not None and parsed != PRECOMPILER_NO_DIRECTIVE_SENTINEL:
                return parsed
    except Exception:
        logger.debug("litellm_proxy: heuristic_exception", exc_info=True)

    if state is None:
        return None

    try:
        return _llm_fallback_precompile(message, state)
    except Exception:
        logger.debug("litellm_proxy: fallback_exception", exc_info=True)
        return None


class ContextCompilerPreCallHookWithPreprocessor(CustomLogger):
    async def async_pre_call_hook(
        self,
        user_api_key_dict: Any,
        cache: Any,
        data: dict[str, object],
        call_type: str,
    ) -> dict[str, object] | str:
        del user_api_key_dict, cache
        logger.debug("litellm_proxy: call_type=%s", call_type)
        if call_type not in _SUPPORTED_CALL_TYPES:
            return data

        request_messages = _extract_request_messages(data)
        logger.debug("litellm_proxy: message_count=%d", len(request_messages))

        user_transcript = _extract_user_transcript(request_messages)
        logger.debug("litellm_proxy: transcript_len=%d", len(user_transcript))

        transcript_for_replay = user_transcript
        replaced_last_user_message = False
        precompiled: str | None = None

        if user_transcript:
            last_user_content = cast(str, user_transcript[-1]["content"])
            prior_state = _state_before_last_message(user_transcript)
            precompiled = _precompile_last_user_message(last_user_content, prior_state)
            logger.debug("litellm_proxy: precompiled=%r", precompiled)
            if precompiled:
                transcript_for_replay = [*user_transcript]
                transcript_for_replay[-1] = {"role": "user", "content": precompiled}
                replaced_last_user_message = True

        logger.debug("litellm_proxy: replaced_last_user_message=%s", replaced_last_user_message)

        replay_result = compile_transcript(transcript_for_replay)
        logger.debug("litellm_proxy: replay_kind=%s", replay_result["kind"])

        if replay_result["kind"] == "confirm":
            # Returning a string from this pre-call hook blocks the upstream
            # LiteLLM model call under LiteLLM callback semantics.
            logger.debug("litellm_proxy: blocking_on_confirm=true")
            return replay_result["prompt_to_user"] or "Confirmation required."

        compiled_state = replay_result["state"]
        system_message: dict[str, object] = {
            "role": "system",
            "content": "You are a helpful assistant.\n"
            + _render_compiled_state_contract(compiled_state),
        }
        logger.debug("litellm_proxy: inject_system_message=true")
        # Preserve original request messages; only compiler replay input uses
        # the preprocessed latest user message when available.
        data["messages"] = [system_message, *request_messages]
        return data


proxy_handler_instance = ContextCompilerPreCallHookWithPreprocessor()
