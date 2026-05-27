"""Minimal LiteLLM Proxy pre-call hook example.

Architecture:
- Replay user transcript through Context Compiler before any model call.
- If clarification is required, block upstream model call.
- Otherwise inject compiled state guidance into a system message.
"""

import logging
from typing import Any

try:
    from litellm.integrations.custom_logger import CustomLogger
except ModuleNotFoundError:
    # Keep this import path optional: CI/tests run without integration extras.
    # A tiny fallback base class keeps module imports deterministic so coverage
    # validates behavior instead of failing or silently skipping on missing litellm.
    class CustomLogger:  # type: ignore[no-redef]
        pass


from context_compiler import (
    POLICY_PROHIBIT,
    State,
    Transcript,
    compile_transcript,
    get_policy_items,
    get_premise_value,
)

logger = logging.getLogger(__name__)

_SUPPORTED_CALL_TYPES = {
    "completion",
    "acompletion",
    "chat_completion",
    "achat_completion",
}


def _render_compiled_state_contract(compiled_state: State) -> str:
    prohibited = get_policy_items(compiled_state, POLICY_PROHIBIT)
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


class ContextCompilerPreCallHook(CustomLogger):
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
        replay_result = compile_transcript(user_transcript)
        logger.debug("litellm_proxy: replay_kind=%s", replay_result["kind"])

        if replay_result["kind"] == "confirm":
            # Returning a string from this pre-call hook blocks the upstream
            # LiteLLM model call under LiteLLM callback semantics.
            logger.debug("litellm_proxy: blocking_on_confirm=true")
            return replay_result["prompt_to_user"] or "Confirmation required."

        compiled_state = replay_result["state"]
        # For long-running conversations, you can optionally compact transcripts by removing user inputs that were compiled into state. See Demo 6.  # noqa: E501
        system_message: dict[str, object] = {
            "role": "system",
            "content": "You are a helpful assistant.\n"
            + _render_compiled_state_contract(compiled_state),
        }
        # Prepend one compiler contract system message, then forward the original
        # request messages unchanged. Existing system messages are preserved.
        logger.debug("litellm_proxy: inject_system_message=true")
        data["messages"] = [system_message, *request_messages]
        return data


proxy_handler_instance = ContextCompilerPreCallHook()
