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


def test_pipe_normal_update_returns_local_ack_and_persists_checkpoint(monkeypatch) -> None:
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


def test_pipe_update_directives_return_local_ack_across_shapes(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_update_shapes", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    forwarded_payloads: list[dict[str, object]] = []

    async def _track_downstream(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        forwarded_payloads.append(payload)
        return {"ok": True}

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
            {"model": "pipe-model", "messages": [{"role": "user", "content": "use docker"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-idempotent",
        )
    )
    assert result == "State updated: Use docker."

    result = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "use docker"}],
            },
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
    assert len(forwarded_payloads) == 0


def test_pipe_show_state_returns_local_summary_and_no_downstream(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_show_state", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    downstream_calls = 0

    async def _track_downstream(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        del payload
        nonlocal downstream_calls
        downstream_calls += 1
        return {"choices": [{"message": {"content": "downstream"}}]}

    module.generate_chat_completion = _track_downstream

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True
    chat_id = "chat-show-state"

    no_pending = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "show state"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__=chat_id,
        )
    )
    assert no_pending == ("Premise: none\nUse: none\nProhibit: none\nPending clarification: no")

    assert downstream_calls == 0
    assert "Context Compiler trace" not in no_pending


def test_pipe_show_state_reports_pending_yes(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_show_state_pending", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    class _PendingEngine:
        state = {"premise": None, "policies": {}, "version": 2}

        def has_pending_clarification(self) -> bool:
            return True

        def step(self, _: str) -> dict[str, object]:
            raise AssertionError("show state should not step engine")

    monkeypatch.setattr(module, "create_engine", lambda: _PendingEngine())
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "show state"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-show-state-pending",
        )
    )
    assert result == "Premise: none\nUse: none\nProhibit: none\nPending clarification: yes"


def test_pipe_show_state_non_exact_routes_normally(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_show_state_non_exact", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    downstream_calls = 0

    async def _track_downstream(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        del payload
        nonlocal downstream_calls
        downstream_calls += 1
        return {"choices": [{"message": {"content": "downstream"}}]}

    module.generate_chat_completion = _track_downstream
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"

    result = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "show state please"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-show-state-non-exact",
        )
    )
    assert result == {"choices": [{"message": {"content": "downstream"}}]}
    assert downstream_calls == 1


def test_pipe_show_state_exact_match_is_case_insensitive_after_trim(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_show_state_case_trim", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    downstream_calls = 0

    async def _track_downstream(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        del payload
        nonlocal downstream_calls
        downstream_calls += 1
        return {"choices": [{"message": {"content": "downstream"}}]}

    module.generate_chat_completion = _track_downstream

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "  ShOw StAtE  "}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-show-state-case-trim",
        )
    )

    assert result == "Premise: none\nUse: none\nProhibit: none\nPending clarification: no"
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
    ("confirmation", "expected_policies"),
    [
        ("yes", {"docker": "use"}),
        ("YES!", {"docker": "use"}),
        (" yes please ", {"docker": "use"}),
        ("no thanks.", {}),
    ],
)
def test_pipe_confirmation_update_returns_local_ack(
    monkeypatch,
    confirmation: str,
    expected_policies: dict[str, str],
) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_confirmation_ack", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    forwarded_payloads: list[dict[str, object]] = []

    async def _track_downstream(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        forwarded_payloads.append(payload)
        return {"ok": True}

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
    assert resumed == "State updated."
    assert len(forwarded_payloads) == 0

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
    assert "active state:" in content
    assert "state injected: no" in content


def test_pipe_trace_on_passthrough_stream_appends_trace_after_chunks(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_trace_on_stream", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    async def _streaming_response() -> object:
        for part in ("down", "stream"):
            yield part

    async def _chat_completion(_: object, payload: dict[str, object], __: object) -> object:
        del payload
        return _streaming_response()

    module.generate_chat_completion = _chat_completion
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-trace-on-stream",
        )
    )

    async def _collect() -> str:
        parts: list[str] = []
        async for chunk in result:
            assert isinstance(chunk, str)
            parts.append(chunk)
        return "".join(parts)

    content = asyncio.run(_collect())
    assert content.startswith("downstream")
    assert "Context Compiler trace" in content
    assert "decision kind: passthrough" in content
    assert "downstream LLM call: yes" in content
    assert "active state:" in content
    assert "state injected: no" in content


def test_pipe_trace_on_update_shows_local_ack_and_no_downstream_call(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_trace_update", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    downstream_calls = 0

    async def _track_downstream(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        nonlocal downstream_calls
        downstream_calls += 1
        del payload
        return {"choices": [{"message": {"content": "downstream"}}]}

    module.generate_chat_completion = _track_downstream

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "prohibit peanuts"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-trace-update",
        )
    )
    assert isinstance(result, str)
    content = result
    assert content.startswith("State updated: Prohibit peanuts.")
    assert "Context Compiler trace" in content
    assert "decision kind: update" in content
    assert "downstream LLM call: no" in content
    assert "state change:" in content
    assert "active state:" in content
    assert "state injected: no" in content
    assert "\n\ndecision kind: update" in content
    assert "\n\nstate injected: no" in content
    assert downstream_calls == 0


def test_pipe_trace_on_clarify_shows_prompt_and_no_downstream_call(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_trace_clarify", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    downstream_calls = 0

    async def _track_downstream(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        nonlocal downstream_calls
        downstream_calls += 1
        del payload
        return {"choices": [{"message": {"content": "downstream"}}]}

    module.generate_chat_completion = _track_downstream

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True

    result = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "set premise to concise answers"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-trace-clarify",
        )
    )
    assert isinstance(result, str)
    assert "decision kind: clarify" in result
    assert "active state:" in result
    assert "clarification prompt:" in result
    assert "downstream LLM call: no" in result
    assert "state injected: no" in result
    assert downstream_calls == 0


def test_pipe_trace_appends_on_object_response_for_passthrough_and_update(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_trace_object_response", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    class _Message:
        def __init__(self, content: str) -> None:
            self.content = content

    class _Choice:
        def __init__(self, content: str) -> None:
            self.message = _Message(content)

    class _Response:
        def __init__(self, content: str) -> None:
            self.choices = [_Choice(content)]

    forwarded_payloads: list[dict[str, object]] = []

    async def _chat_completion(_: object, payload: dict[str, object], __: object) -> object:
        forwarded_payloads.append(payload)
        return _Response("downstream")

    module.generate_chat_completion = _chat_completion
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True

    passthrough = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-object-passthrough",
        )
    )
    assert hasattr(passthrough, "choices")
    passthrough_content = passthrough.choices[0].message.content
    assert "Context Compiler trace" in passthrough_content
    assert "decision kind: passthrough" in passthrough_content
    assert "downstream LLM call: yes" in passthrough_content

    update = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "use docker"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-object-update",
        )
    )
    assert isinstance(update, str)
    update_content = update
    assert "Context Compiler trace" in update_content
    assert "decision kind: update" in update_content
    assert "downstream LLM call: no" in update_content
    assert "state injected: no" in update_content
    assert len(forwarded_payloads) == 1


def test_pipe_trace_appends_on_streaming_response_wrapper_passthrough_and_update(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_trace_streaming_wrapper", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    class _StreamingResponse:
        def __init__(self, parts: tuple[str, ...]) -> None:
            async def _iter() -> object:
                for part in parts:
                    yield part

            self.body_iterator = _iter()

    forwarded_payloads: list[dict[str, object]] = []

    async def _chat_completion(_: object, payload: dict[str, object], __: object) -> object:
        forwarded_payloads.append(payload)
        return _StreamingResponse(("data: stub\n\n", "data: [DONE]\n\n"))

    module.generate_chat_completion = _chat_completion
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True

    passthrough = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-stream-wrapper-passthrough",
        )
    )

    async def _collect_stream(wrapper: object) -> str:
        parts: list[str] = []
        async for chunk in wrapper.body_iterator:
            assert isinstance(chunk, str)
            parts.append(chunk)
        return "".join(parts)

    passthrough_stream = asyncio.run(_collect_stream(passthrough))
    assert "data: [DONE]" in passthrough_stream
    assert "Context Compiler trace" in passthrough_stream
    assert "decision kind: passthrough" in passthrough_stream

    update = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "use docker"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-stream-wrapper-update",
        )
    )
    assert isinstance(update, str)
    assert "Context Compiler trace" in update
    assert "decision kind: update" in update
    assert "state injected: no" in update
    assert len(forwarded_payloads) == 1


@pytest.mark.parametrize(
    ("steps", "expected_ack"),
    [
        (
            ["use docker", "clear state"],
            "State cleared.",
        ),
        (
            ["set premise concise replies", "clear premise"],
            "Premise cleared.",
        ),
        (
            ["use docker", "use pytest", "reset policies"],
            "Policies reset.",
        ),
        (
            ["use docker", "remove policy docker"],
            "State updated: Removed policy docker.",
        ),
    ],
)
def test_pipe_trace_update_clear_reset_paths_single_and_consistent(
    monkeypatch,
    steps: list[str],
    expected_ack: str,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_trace_clear_reset", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    downstream_calls = 0

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        nonlocal downstream_calls
        downstream_calls += 1
        del payload
        return {"choices": [{"message": {"content": "downstream"}}]}

    module.generate_chat_completion = _chat_completion
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True

    result: object = ""
    for idx, user_input in enumerate(steps):
        result = asyncio.run(
            pipe.pipe(
                {"model": "pipe-model", "messages": [{"role": "user", "content": user_input}]},
                __user__={"id": "u1"},
                __request__=object(),
                __chat_id__=f"chat-trace-clear-reset-{hash(tuple(steps))}",
            )
        )
        if idx < len(steps) - 1:
            continue

    assert isinstance(result, str)
    assert result.startswith(expected_ack)
    content = result
    assert content.count("Context Compiler trace") == 1
    assert "decision kind: update" in content
    assert "downstream LLM call: no" in content
    assert "downstream LLM call: yes" not in content
    assert "active state: none" in content
    assert "state injected: no" in content
    assert downstream_calls == 0


def test_pipe_clear_state_trace_not_duplicated_when_model_echoes_history(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_trace_echo_dedupe", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        messages = payload.get("messages")
        echoed = ""
        if isinstance(messages, list):
            assistant_contents = [
                str(msg.get("content", ""))
                for msg in messages
                if isinstance(msg, dict) and msg.get("role") == "assistant"
            ]
            echoed = "\n".join(assistant_contents)
        content = "downstream"
        if echoed:
            content += f"\n{echoed}"
        return {"choices": [{"message": {"content": content}}]}

    module.generate_chat_completion = _chat_completion
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True
    chat_id = "chat-trace-echo-dedupe"

    first = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "use docker"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__=chat_id,
        )
    )
    assert isinstance(first, str)
    first_content = first
    assert first_content.count("Context Compiler trace") == 1

    second = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [
                    {"role": "assistant", "content": first_content},
                    {"role": "user", "content": "clear state"},
                ],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__=chat_id,
        )
    )
    assert isinstance(second, str)
    second_content = second
    assert second_content.count("Context Compiler trace") == 1
    assert "decision kind: update" in second_content
    assert "downstream LLM call: no" in second_content
    assert "downstream LLM call: yes" not in second_content
    assert "active state: none" in second_content
    assert "state injected: no" in second_content


def test_pipe_clear_state_strips_preexisting_contradictory_trace_from_model_output(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_trace_strip_contradiction", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    old_trace = (
        "Context Compiler trace\n\n"
        "decision kind: update\n"
        "active state: none\n"
        "downstream LLM call: no\n"
        "\n"
        "state injected: none"
    )

    call_count = 0

    async def _chat_completion(
        _: object,
        payload: dict[str, object],
        __: object,
    ) -> dict[str, object]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"choices": [{"message": {"content": "downstream"}}]}
        del payload
        return {"choices": [{"message": {"content": f"downstream\n{old_trace}"}}]}

    module.generate_chat_completion = _chat_completion
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True
    chat_id = "chat-trace-strip-contradiction"

    _ = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "use docker"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__=chat_id,
        )
    )

    second = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "clear state"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__=chat_id,
        )
    )
    assert isinstance(second, str)
    second_content = second
    assert second_content.count("Context Compiler trace") == 1
    assert "downstream LLM call: no" in second_content
    assert "downstream LLM call: yes" not in second_content


def test_pipe_passthrough_injects_active_state_and_trace_reports_yes(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_pipe_passthrough_state_injection", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    forwarded_payloads: list[dict[str, object]] = []

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        forwarded_payloads.append(payload)
        return {"choices": [{"message": {"content": "answer"}}]}

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True
    chat_id = "chat-passthrough-injected-state"

    update = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "use docker"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__=chat_id,
        )
    )
    assert "State updated: Use docker." in update
    assert len(forwarded_payloads) == 0

    passthrough = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "what container runtime should i use?"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__=chat_id,
        )
    )
    assert isinstance(passthrough, dict)
    assert len(forwarded_payloads) == 1
    messages = forwarded_payloads[0]["messages"]
    assert isinstance(messages, list)
    assert any(
        isinstance(msg, dict)
        and msg.get("role") == "system"
        and isinstance(msg.get("content"), str)
        and msg["content"].startswith("[[cc_state]]")
        and "Use: docker" in msg["content"]
        for msg in messages
    )
    content = passthrough["choices"][0]["message"]["content"]
    assert "state injected: yes" in content
