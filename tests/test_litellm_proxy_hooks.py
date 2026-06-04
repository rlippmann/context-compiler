import asyncio
import importlib.util
import sys
import types
from copy import deepcopy
from pathlib import Path

BASIC_PROXY_PATH = Path("examples/integrations/litellm_proxy/context_compiler_precall_hook.py")
PREPROC_PROXY_PATH = Path(
    "examples/integrations/litellm_proxy/context_compiler_precall_hook_with_preprocessor.py"
)


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_proxy_module_with_stubs(monkeypatch, module_name: str, path: Path):
    litellm_mod = types.ModuleType("litellm")
    integrations_mod = types.ModuleType("litellm.integrations")
    custom_logger_mod = types.ModuleType("litellm.integrations.custom_logger")

    class _CustomLogger:
        pass

    custom_logger_mod.CustomLogger = _CustomLogger

    monkeypatch.setitem(sys.modules, "litellm", litellm_mod)
    monkeypatch.setitem(sys.modules, "litellm.integrations", integrations_mod)
    monkeypatch.setitem(sys.modules, "litellm.integrations.custom_logger", custom_logger_mod)

    return _load_module(module_name, path)


def _state(
    *, premise: str | None = None, policies: dict[str, str] | None = None
) -> dict[str, object]:
    return {
        "premise": premise,
        "policies": {} if policies is None else policies,
        "version": 2,
    }


def test_basic_proxy_hook_unsupported_call_type_returns_data_unchanged(monkeypatch) -> None:
    module = _load_proxy_module_with_stubs(
        monkeypatch, "litellm_proxy_basic_unsupported_call_type", BASIC_PROXY_PATH
    )
    hook = module.ContextCompilerPreCallHook()
    data = {"messages": [{"role": "user", "content": "hello"}], "model": "demo"}

    result = asyncio.run(hook.async_pre_call_hook(None, None, data, "embeddings"))

    assert result is data


def test_basic_proxy_hook_clarify_returns_prompt_string_and_blocks_upstream(monkeypatch) -> None:
    module = _load_proxy_module_with_stubs(
        monkeypatch, "litellm_proxy_basic_clarify", BASIC_PROXY_PATH
    )
    hook = module.ContextCompilerPreCallHook()
    captured: list[list[dict[str, str]]] = []

    def _compile_transcript(transcript: list[dict[str, str]]) -> dict[str, object]:
        captured.append(transcript)
        return {"kind": "confirm", "prompt_to_user": 'Did you mean to use "kubectl" instead?'}

    monkeypatch.setattr(module, "compile_transcript", _compile_transcript)
    data = {
        "model": "demo",
        "messages": [{"role": "user", "content": "use kubectl instead of docker"}],
    }

    result = asyncio.run(hook.async_pre_call_hook(None, None, data, "completion"))

    assert result == 'Did you mean to use "kubectl" instead?'
    assert captured == [[{"role": "user", "content": "use kubectl instead of docker"}]]
    assert data["messages"] == [{"role": "user", "content": "use kubectl instead of docker"}]


def test_basic_proxy_hook_update_prepends_one_system_contract_message(monkeypatch) -> None:
    module = _load_proxy_module_with_stubs(
        monkeypatch, "litellm_proxy_basic_update", BASIC_PROXY_PATH
    )
    hook = module.ContextCompilerPreCallHook()
    original_messages = [
        {"role": "system", "content": "original system"},
        {"role": "user", "content": "prohibit peanuts"},
    ]
    data = {"model": "demo", "messages": deepcopy(original_messages)}

    monkeypatch.setattr(
        module,
        "compile_transcript",
        lambda _transcript: {"kind": "state", "state": _state(policies={"peanuts": "prohibit"})},
    )

    result = asyncio.run(hook.async_pre_call_hook(None, None, data, "completion"))

    assert result is data
    assert isinstance(data["messages"], list)
    messages = data["messages"]
    assert len(messages) == len(original_messages) + 1
    assert messages[0]["role"] == "system"
    assert "Host policy contract:" in messages[0]["content"]
    assert "Never recommend or use prohibited items: peanuts." in messages[0]["content"]
    assert messages[1:] == original_messages


def test_basic_proxy_hook_passthrough_preserves_original_messages_after_injected_contract(
    monkeypatch,
) -> None:
    module = _load_proxy_module_with_stubs(
        monkeypatch, "litellm_proxy_basic_passthrough_contract", BASIC_PROXY_PATH
    )
    hook = module.ContextCompilerPreCallHook()
    original_messages = [
        {"role": "system", "content": "original system"},
        {"role": "assistant", "content": "earlier reply"},
        {"role": "user", "content": "hello there"},
    ]
    data = {"model": "demo", "messages": deepcopy(original_messages)}

    monkeypatch.setattr(
        module,
        "compile_transcript",
        lambda _transcript: {"kind": "state", "state": _state()},
    )

    result = asyncio.run(hook.async_pre_call_hook(None, None, data, "chat_completion"))

    assert result is data
    assert data["messages"][1:] == original_messages
    assert data["messages"][0]["role"] == "system"
    assert "Host policy contract:" in data["messages"][0]["content"]


def test_basic_proxy_hook_extracts_only_user_text_messages_from_mixed_content_shapes(
    monkeypatch,
) -> None:
    module = _load_proxy_module_with_stubs(
        monkeypatch, "litellm_proxy_basic_extract_user_text", BASIC_PROXY_PATH
    )
    messages = [
        {"role": "system", "content": "system"},
        {"role": "assistant", "content": "assistant text"},
        {"role": "user", "content": "plain user text"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "alpha"},
                {"type": "image_url", "image_url": {"url": "https://example.test/image.png"}},
                {"type": "text", "text": "beta"},
            ],
        },
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "ignored"}}]},
        {"role": "user", "content": {"type": "text", "text": "ignored non-list shape"}},
    ]

    transcript = module._extract_user_transcript(messages)

    assert transcript == [
        {"role": "user", "content": "plain user text"},
        {"role": "user", "content": "alpha beta"},
    ]


def test_preprocessor_proxy_hook_only_rewrites_latest_user_message_for_replay(monkeypatch) -> None:
    module = _load_proxy_module_with_stubs(
        monkeypatch, "litellm_proxy_preproc_rewrites_latest_only", PREPROC_PROXY_PATH
    )
    hook = module.ContextCompilerPreCallHookWithPreprocessor()
    compile_calls: list[list[dict[str, str]]] = []

    def _compile_transcript(transcript: list[dict[str, str]]) -> dict[str, object]:
        compile_calls.append(transcript)
        if len(compile_calls) == 1:
            return {"kind": "state", "state": _state()}
        return {"kind": "state", "state": _state(policies={"docker": "use"})}

    monkeypatch.setattr(module, "compile_transcript", _compile_transcript)
    monkeypatch.setattr(
        module, "_preprocess_last_user_message", lambda _message, _state: "use docker"
    )

    data = {
        "model": "demo",
        "messages": [
            {"role": "user", "content": "hello there"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "please use docker"},
        ],
    }

    result = asyncio.run(hook.async_pre_call_hook(None, None, data, "completion"))

    assert result is data
    assert compile_calls == [
        [{"role": "user", "content": "hello there"}],
        [
            {"role": "user", "content": "hello there"},
            {"role": "user", "content": "use docker"},
        ],
    ]


def test_preprocessor_proxy_hook_does_not_rewrite_forwarded_request_messages(monkeypatch) -> None:
    module = _load_proxy_module_with_stubs(
        monkeypatch, "litellm_proxy_preproc_preserves_forwarded_messages", PREPROC_PROXY_PATH
    )
    hook = module.ContextCompilerPreCallHookWithPreprocessor()
    original_messages = [
        {"role": "system", "content": "original system"},
        {"role": "user", "content": "please use docker"},
    ]
    data = {"model": "demo", "messages": deepcopy(original_messages)}

    compile_calls: list[list[dict[str, str]]] = []

    def _compile_transcript(transcript: list[dict[str, str]]) -> dict[str, object]:
        compile_calls.append(transcript)
        if len(compile_calls) == 1:
            return {"kind": "state", "state": _state()}
        return {"kind": "state", "state": _state(policies={"docker": "use"})}

    monkeypatch.setattr(module, "compile_transcript", _compile_transcript)
    monkeypatch.setattr(
        module, "_preprocess_last_user_message", lambda _message, _state: "use docker"
    )

    result = asyncio.run(hook.async_pre_call_hook(None, None, data, "completion"))

    assert result is data
    assert data["messages"][1:] == original_messages
    assert data["messages"][2]["content"] == "please use docker"
    assert compile_calls[-1] == [{"role": "user", "content": "use docker"}]


def test_preprocessor_proxy_hook_abstain_leaves_replay_input_unchanged(monkeypatch) -> None:
    module = _load_proxy_module_with_stubs(
        monkeypatch, "litellm_proxy_preproc_abstain_unchanged", PREPROC_PROXY_PATH
    )
    hook = module.ContextCompilerPreCallHookWithPreprocessor()
    compile_calls: list[list[dict[str, str]]] = []

    def _compile_transcript(transcript: list[dict[str, str]]) -> dict[str, object]:
        compile_calls.append(transcript)
        return {"kind": "state", "state": _state()}

    monkeypatch.setattr(module, "compile_transcript", _compile_transcript)
    monkeypatch.setattr(module, "_state_before_last_message", lambda _transcript: _state())
    monkeypatch.setattr(module, "_preprocess_last_user_message", lambda _message, _state: None)

    data = {
        "model": "demo",
        "messages": [
            {"role": "user", "content": "first user turn"},
            {"role": "assistant", "content": "assistant reply"},
            {"role": "user", "content": "i think we should use docker"},
        ],
    }

    result = asyncio.run(hook.async_pre_call_hook(None, None, data, "completion"))

    assert result is data
    assert compile_calls == [
        [
            {"role": "user", "content": "first user turn"},
            {"role": "user", "content": "i think we should use docker"},
        ]
    ]


def test_preprocessor_proxy_hook_invalid_fallback_output_does_not_mutate_replay_input(
    monkeypatch,
) -> None:
    module = _load_proxy_module_with_stubs(
        monkeypatch, "litellm_proxy_preproc_invalid_fallback_unchanged", PREPROC_PROXY_PATH
    )
    hook = module.ContextCompilerPreCallHookWithPreprocessor()
    compile_calls: list[list[dict[str, str]]] = []

    def _compile_transcript(transcript: list[dict[str, str]]) -> dict[str, object]:
        compile_calls.append(transcript)
        return {"kind": "state", "state": _state()}

    monkeypatch.setattr(module, "compile_transcript", _compile_transcript)
    monkeypatch.setattr(
        module,
        "preprocess_heuristic",
        lambda _text: {"outcome": "no_directive", "directive": None},
    )
    monkeypatch.setattr(module, "_llm_fallback_preprocess", lambda _message, _state: None)

    data = {
        "model": "demo",
        "messages": [
            {"role": "user", "content": "first user turn"},
            {"role": "assistant", "content": "assistant reply"},
            {"role": "user", "content": "please use docker"},
        ],
    }

    result = asyncio.run(hook.async_pre_call_hook(None, None, data, "completion"))

    assert result is data
    assert compile_calls == [
        [{"role": "user", "content": "first user turn"}],
        [
            {"role": "user", "content": "first user turn"},
            {"role": "user", "content": "please use docker"},
        ],
    ]
