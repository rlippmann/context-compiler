import asyncio
import builtins
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

MODULE_PATH = Path("examples/integrations/openwebui/open_webui_pipe.py")


def _load_module_with_openwebui_stubs(module_name: str, monkeypatch):
    fastapi_mod = types.ModuleType("fastapi")

    class _Request:
        pass

    fastapi_mod.Request = _Request

    open_webui_mod = types.ModuleType("open_webui")
    open_webui_models_mod = types.ModuleType("open_webui.models")
    open_webui_models_users_mod = types.ModuleType("open_webui.models.users")
    open_webui_utils_mod = types.ModuleType("open_webui.utils")
    open_webui_utils_chat_mod = types.ModuleType("open_webui.utils.chat")

    class _Users:
        @staticmethod
        def get_user_by_id(user_id: object) -> dict[str, object]:
            return {"id": user_id}

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        return {"choices": [{"message": {"content": payload.get("_mock_content", "")}}]}

    open_webui_models_users_mod.Users = _Users
    open_webui_utils_chat_mod.generate_chat_completion = _chat_completion

    sys.modules["fastapi"] = fastapi_mod
    sys.modules["open_webui"] = open_webui_mod
    sys.modules["open_webui.models"] = open_webui_models_mod
    sys.modules["open_webui.models.users"] = open_webui_models_users_mod
    sys.modules["open_webui.utils"] = open_webui_utils_mod
    sys.modules["open_webui.utils.chat"] = open_webui_utils_chat_mod

    real_import = builtins.__import__

    def _guarded_import(
        name: str,
        globals_: dict[str, object] | None = None,
        locals_: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "pydantic":
            raise ModuleNotFoundError("No module named 'pydantic'")
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _guarded_import)

    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_openwebui_pipe_imports_without_pydantic(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_no_pydantic", monkeypatch)
    pipe = module.Pipe()
    assert pipe.valves.BASE_MODEL_ID == ""


def test_pipe_restore_and_persist_checkpoint_points(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_checkpoint", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY["chat-1"] = "ckpt-in"

    class _FakeEngine:
        def __init__(self, kind: str, checkpoint_out: str) -> None:
            self.kind = kind
            self.state = {"premise": None, "policies": {}, "version": 2}
            self.imported: list[str] = []
            self._checkpoint_out = checkpoint_out
            self.export_calls = 0

        def import_checkpoint_json(self, payload: str) -> None:
            self.imported.append(payload)

        def export_checkpoint_json(self) -> str:
            self.export_calls += 1
            return self._checkpoint_out

        def export_checkpoint(self) -> dict[str, object]:
            return {
                "checkpoint_version": 1,
                "authoritative_state": self.state,
                "pending": None,
            }

        def step(self, _text: str) -> dict[str, object]:
            if self.kind == "clarify":
                return {"kind": "clarify", "prompt_to_user": "confirm?", "state": None}
            return {"kind": self.kind, "state": self.state}

    created: list[_FakeEngine] = []

    def _create_engine():
        engine = _FakeEngine("clarify", "ckpt-clarify")
        created.append(engine)
        return engine

    monkeypatch.setattr(module, "create_engine", _create_engine)
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "test"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-1",
        )
    )
    assert result == "confirm?"
    assert created[0].imported == ["ckpt-in"]
    assert module._CHECKPOINTS_BY_CHAT_KEY["chat-1"] == "ckpt-clarify"
    assert created[0].export_calls == 1

    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY["chat-2"] = "ckpt-keep"

    passthrough_engine = _FakeEngine("passthrough", "ckpt-new")
    monkeypatch.setattr(module, "create_engine", lambda: passthrough_engine)
    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-2",
        )
    )
    assert isinstance(result, dict)
    assert passthrough_engine.imported == ["ckpt-keep"]
    assert passthrough_engine.export_calls == 0
    assert module._CHECKPOINTS_BY_CHAT_KEY["chat-2"] == "ckpt-keep"


def test_pipe_requires_base_model_id(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_requires_base", monkeypatch)
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = ""

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
        )
    )

    assert result == "Context Compiler pipe misconfigured: BASE_MODEL_ID is required."


def test_pipe_blocks_recursive_base_model_id(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_recursion_guard", monkeypatch)
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "pipe-model"

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
        )
    )

    assert result == (
        "Context Compiler pipe misconfigured: BASE_MODEL_ID must not match "
        "the selected pipe model id to avoid recursive routing."
    )


def test_pipe_normalizes_model_not_found_response(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_model_not_found_response", monkeypatch)
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        del payload
        return {"error": {"message": "MODEL NOT FOUND"}}

    module.generate_chat_completion = _chat_completion

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
        )
    )

    assert result == (
        "Context Compiler pipe misconfigured: BASE_MODEL_ID is invalid or not "
        "configured in Open WebUI. Configure a valid model id in "
        "Admin Panel → Settings → Models."
    )


def test_pipe_normalizes_model_not_found_exception(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_model_not_found_exception", monkeypatch)
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"

    class _ForwardError(Exception):
        def __init__(self) -> None:
            super().__init__("forward failed")
            self.detail = {"error": {"message": "model not found"}}

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        del payload
        raise _ForwardError()

    module.generate_chat_completion = _chat_completion

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
        )
    )

    assert result == (
        "Context Compiler pipe misconfigured: BASE_MODEL_ID is invalid or not "
        "configured in Open WebUI. Configure a valid model id in "
        "Admin Panel → Settings → Models."
    )


def test_pipe_supports_async_user_lookup(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_async_user_lookup", monkeypatch)
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"

    async def _get_user_by_id(user_id: object) -> dict[str, object]:
        return {"id": user_id}

    monkeypatch.setattr(module.Users, "get_user_by_id", _get_user_by_id)

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
        )
    )

    assert isinstance(result, dict)


def test_pipe_normal_update_returns_deterministic_ack_and_persists_checkpoint(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_update_forward", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    forwarded_payloads: list[dict[str, object]] = []

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        forwarded_payloads.append(payload)
        return {"ok": True}

    module.generate_chat_completion = _chat_completion

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    chat_key = "chat-normal-update"

    result = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "prohibit peanuts"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__=chat_key,
        )
    )

    assert result == "State updated: Prohibit peanuts."
    assert len(forwarded_payloads) == 0

    checkpoint = json.loads(module._CHECKPOINTS_BY_CHAT_KEY[chat_key])
    assert checkpoint["pending"] is None
    assert checkpoint["authoritative_state"]["policies"] == {"peanuts": "prohibit"}

    result = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "remove policy peanuts"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__=chat_key,
        )
    )

    assert result == "State updated: Removed policy peanuts."
    assert len(forwarded_payloads) == 0

    checkpoint = json.loads(module._CHECKPOINTS_BY_CHAT_KEY[chat_key])
    assert checkpoint["pending"] is None
    assert checkpoint["authoritative_state"]["policies"] == {}


def test_pipe_literal_replacement_update_summary_uses_new_item_only(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_literal_replace_summary", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    downstream_calls = 0

    async def _track_downstream(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        nonlocal downstream_calls
        downstream_calls += 1
        raise AssertionError(f"downstream model should not be called: {payload.get('model')}")

    module.generate_chat_completion = _track_downstream

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "use   DOCKER"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-use",
        )
    )
    assert result == "State updated: Use docker."

    result = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "prohibit DOCKER"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-prohibit",
        )
    )
    assert result == "State updated: Prohibit docker."

    result = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "remove policy DOCKER"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-remove",
        )
    )
    assert result == "State updated: Removed policy docker."

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "use docker"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-replace",
        )
    )
    assert result == "State updated: Use docker."

    result = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "use KUBECTL instead of DOCKER"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-replace",
        )
    )
    assert result == "State updated: Use kubectl."

    result = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "set premise concise answers"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-premise",
        )
    )
    assert result == "State updated."

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "clear premise"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-premise",
        )
    )
    assert result == "Premise cleared."

    result = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "use docker instead of docker"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-replace-noop",
        )
    )
    assert result == "State updated: Use docker."
    assert downstream_calls == 0


def test_pipe_near_miss_directives_return_deterministic_clarify_without_downstream(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_near_miss_clarify", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    downstream_calls = 0

    async def _track_downstream(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        nonlocal downstream_calls
        downstream_calls += 1
        raise AssertionError(f"downstream model should not be called: {payload.get('model')}")

    module.generate_chat_completion = _track_downstream

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"

    cases = [
        ("reset premise", "Unknown directive.\nUse 'clear premise' or 'reset policies'."),
        ("reset premises", "Unknown directive.\nUse 'clear premise' or 'reset policies'."),
        ("clear premises", "Unknown directive.\nUse 'clear premise' or 'reset policies'."),
        ("set premise to concise answers", "Invalid premise syntax.\nUse 'set premise <value>'."),
        (
            "change premise formal tone",
            "Invalid premise syntax.\nUse 'change premise to <value>'.",
        ),
    ]

    for idx, (user_input, expected) in enumerate(cases):
        result = asyncio.run(
            pipe.pipe(
                {"model": "pipe-model", "messages": [{"role": "user", "content": user_input}]},
                __user__={"id": "u1"},
                __request__=object(),
                __chat_id__=f"chat-near-miss-{idx}",
            )
        )
        assert result == expected

    assert downstream_calls == 0


@pytest.mark.parametrize(
    ("confirmation", "expected_policies", "expected_response"),
    [
        ("yes", {"docker": "use"}, "State updated: Use docker."),
        ("YES!", {"docker": "use"}, "State updated: Use docker."),
        (" yes please ", {"docker": "use"}, "State updated: Use docker."),
        ("no thanks.", {}, "State unchanged."),
    ],
)
def test_pipe_confirmation_update_returns_ack_without_downstream_model_call(
    monkeypatch,
    confirmation: str,
    expected_policies: dict[str, str],
    expected_response: str,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_confirmation_ack", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    downstream_calls = 0

    async def _track_downstream(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        nonlocal downstream_calls
        downstream_calls += 1
        raise AssertionError(f"downstream model should not be called: {payload.get('model')}")

    module.generate_chat_completion = _track_downstream

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    chat_key = "chat-confirm-ack"

    clarify = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "use docker instead of kubectl"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__=chat_key,
        )
    )
    assert clarify == 'Did you mean to use "docker" instead?'
    first_checkpoint = json.loads(module._CHECKPOINTS_BY_CHAT_KEY[chat_key])
    assert first_checkpoint["pending"] is not None

    resumed = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": confirmation}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__=chat_key,
        )
    )
    assert resumed == expected_response
    assert downstream_calls == 0

    resumed_engine = module._ENGINES_BY_CHAT_KEY[chat_key]
    assert resumed_engine.state == {
        "premise": None,
        "policies": expected_policies,
        "version": 2,
    }
    resumed_checkpoint = json.loads(module._CHECKPOINTS_BY_CHAT_KEY[chat_key])
    assert resumed_checkpoint["pending"] is None


def test_pipe_trace_off_keeps_existing_response_shape(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_trace_off_shape", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        del payload
        return {"choices": [{"message": {"content": "downstream"}}]}

    module.generate_chat_completion = _chat_completion
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = False

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-trace-off",
        )
    )
    assert result == {"choices": [{"message": {"content": "downstream"}}]}


def test_pipe_trace_on_appends_trace_to_user_visible_output(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_trace_on", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        del payload
        return {"choices": [{"message": {"content": "downstream"}}]}

    module.generate_chat_completion = _chat_completion
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-trace-on",
        )
    )
    content = result["choices"][0]["message"]["content"]
    assert "downstream" in content
    assert "Context Compiler trace" in content
    assert "decision kind: passthrough" in content
    assert "downstream LLM call: yes" in content
