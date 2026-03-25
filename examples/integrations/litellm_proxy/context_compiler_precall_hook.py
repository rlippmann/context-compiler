"""Minimal LiteLLM Proxy pre-call hook example.

Architecture:
- Replay user transcript through Context Compiler before any model call.
- If clarification is required, block upstream model call.
- Otherwise inject compiled state guidance into a system message.
"""

from typing import Any, Literal

from litellm.integrations.custom_logger import CustomLogger  # type: ignore[import-not-found]

from context_compiler import State, compile_transcript, get_policy_items, get_premise_value


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


def _extract_user_transcript(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    transcript: list[dict[str, object]] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role == "user" and isinstance(content, str):
            transcript.append({"role": "user", "content": content})
    return transcript


class ContextCompilerPreCallHook(CustomLogger):  # type: ignore[misc]
    async def async_pre_call_hook(
        self,
        user_api_key_dict: Any,
        cache: Any,
        data: dict[str, object],
        call_type: Literal[
            "completion",
            "text_completion",
            "embeddings",
            "image_generation",
            "moderation",
            "audio_transcription",
        ],
    ) -> dict[str, object] | str:
        del user_api_key_dict, cache
        if call_type not in {"completion", "text_completion"}:
            return data

        request_messages = _extract_request_messages(data)
        user_transcript = _extract_user_transcript(request_messages)
        replay_result = compile_transcript(user_transcript)

        if replay_result["kind"] == "confirm":
            # Intentional minimal blocking behavior: for completion/text completion
            # calls, returning a string here is treated by LiteLLM as a rejected
            # assistant response, so the upstream model call is not executed.
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
        data["messages"] = [system_message, *request_messages]
        return data


proxy_handler_instance = ContextCompilerPreCallHook()
