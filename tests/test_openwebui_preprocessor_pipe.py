import asyncio
import builtins
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any, cast

import pytest

MODULE_PATH = Path("examples/integrations/openwebui/open_webui_pipe_with_preprocessor.py")


class DummyValves:
    def __init__(
        self,
        base_model_id: str | None,
        preprocessor_model_id: str | None,
        allow_missing_base: bool = False,
    ) -> None:
        self.BASE_MODEL_ID = base_model_id
        self.PREPROCESSOR_MODEL_ID = preprocessor_model_id
        self.ALLOW_MISSING_BASE_MODEL_FOR_DEBUG = allow_missing_base
        self.PREPROCESSOR_PROMPT_PROFILE = "default"
        self.SHOW_CONTEXT_COMPILER_TRACE = False


def _load_module_with_openwebui_stubs(
    module_name: str, monkeypatch, *, block_pydantic: bool = True
):
    fastapi_mod = types.ModuleType("fastapi")

    class _Request:  # minimal placeholder for type import
        pass

    fastapi_mod.Request = _Request

    open_webui_mod = types.ModuleType("open_webui")
    open_webui_models_mod = types.ModuleType("open_webui.models")
    open_webui_models_users_mod = types.ModuleType("open_webui.models.users")
    open_webui_utils_mod = types.ModuleType("open_webui.utils")
    open_webui_utils_chat_mod = types.ModuleType("open_webui.utils.chat")
    open_webui_utils_models_mod = types.ModuleType("open_webui.utils.models")

    class _Users:
        @staticmethod
        def get_user_by_id(user_id: object) -> dict[str, object]:
            return {"id": user_id}

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        return {"choices": [{"message": {"content": payload.get("_mock_content", "")}}]}

    async def _all_models(_: object, user: object = None) -> list[dict[str, str]]:
        del user
        return [{"id": "base-model"}, {"id": "prep-model"}, {"id": "pipe-model"}]

    open_webui_models_users_mod.Users = _Users
    open_webui_utils_chat_mod.generate_chat_completion = _chat_completion
    open_webui_utils_models_mod.get_all_models = _all_models

    sys.modules["fastapi"] = fastapi_mod
    sys.modules["open_webui"] = open_webui_mod
    sys.modules["open_webui.models"] = open_webui_models_mod
    sys.modules["open_webui.models.users"] = open_webui_models_users_mod
    sys.modules["open_webui.utils"] = open_webui_utils_mod
    sys.modules["open_webui.utils.chat"] = open_webui_utils_chat_mod
    sys.modules["open_webui.utils.models"] = open_webui_utils_models_mod
    if block_pydantic:
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


def test_preprocessor_model_defaults_to_base_model(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_defaults", monkeypatch)
    pipe = module.Pipe()
    pipe.valves = DummyValves("base-model", None)

    assert pipe._resolve_preprocessor_model_id("base-model") == "base-model"


def test_preprocessor_model_empty_string_defaults_to_base_model(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_defaults_empty", monkeypatch)
    pipe = module.Pipe()
    pipe.valves = DummyValves("base-model", "")

    assert pipe._resolve_preprocessor_model_id("base-model") == "base-model"


def test_pipe_requires_base_model_id_when_debug_disabled(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_requires_base", monkeypatch)
    pipe = module.Pipe()
    pipe.valves = DummyValves("", None, allow_missing_base=False)

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hi"}]},
            __user__={"id": "u1"},
            __request__=object(),
        )
    )

    assert result == (
        "Context Compiler pipe misconfigured: BASE_MODEL_ID is required "
        "(or set ALLOW_MISSING_BASE_MODEL_FOR_DEBUG=true for testing)."
    )


def test_preprocessor_model_can_be_overridden(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_override", monkeypatch)
    pipe = module.Pipe()
    pipe.valves = DummyValves("base-model", "prep-model")

    assert pipe._resolve_preprocessor_model_id("base-model") == "prep-model"


def test_pipe_debug_false_missing_base_blocks_without_llm_calls(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_debug_false_blocked", monkeypatch)
    pipe = module.Pipe()
    pipe.valves = DummyValves(None, None, allow_missing_base=False)

    llm_calls = 0

    async def _chat_completion(_: object, payload: dict[str, Any], __: object) -> dict[str, object]:
        del payload
        nonlocal llm_calls
        llm_calls += 1
        return {"ok": True}

    module.generate_chat_completion = _chat_completion

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hi"}]},
            __user__={"id": "u1"},
            __request__=object(),
        )
    )

    assert result == (
        "Context Compiler pipe misconfigured: BASE_MODEL_ID is required "
        "(or set ALLOW_MISSING_BASE_MODEL_FOR_DEBUG=true for testing)."
    )
    assert llm_calls == 0


def test_pipe_debug_true_missing_base_skips_update_forwarding_call(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_debug_true_allowed", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()
    pipe = module.Pipe()
    pipe.valves = DummyValves(None, None, allow_missing_base=True)

    llm_calls = 0

    async def _chat_completion(_: object, payload: dict[str, Any], __: object) -> dict[str, object]:
        del payload
        nonlocal llm_calls
        llm_calls += 1
        return {"ok": True}

    module.generate_chat_completion = _chat_completion
    module.preprocess_heuristic = lambda _text: {
        "outcome": module.PREPROCESS_OUTCOME_DIRECTIVE,
        "directive": "use docker",
    }
    module.parse_preprocessor_output = lambda value, **_kwargs: value

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "please use docker"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-missing-base-debug",
        )
    )

    assert result == "State updated: Use docker."
    assert llm_calls == 0


def test_pipe_debug_true_missing_base_hello_returns_base_misconfig_without_llm_calls(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_debug_true_hello_safe", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()
    pipe = module.Pipe()
    pipe.valves = DummyValves(None, None, allow_missing_base=True)

    llm_calls = 0

    async def _chat_completion(_: object, payload: dict[str, Any], __: object) -> dict[str, object]:
        del payload
        nonlocal llm_calls
        llm_calls += 1
        return {"ok": True}

    module.generate_chat_completion = _chat_completion
    module.preprocess_heuristic = lambda _text: {
        "outcome": "no_directive",
        "directive": None,
    }

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-missing-base-debug-hello",
        )
    )

    assert result == (
        "Context Compiler debug mode: BASE_MODEL_ID is empty; skipping model passthrough."
    )
    assert llm_calls == 0


@pytest.mark.parametrize(
    "flag_value",
    ["true", "1", "on", True],
)
def test_pipe_debug_true_like_values_missing_base_hello_uses_debug_passthrough_message(
    monkeypatch, flag_value
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_debug_truthy_values", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()
    pipe = module.Pipe()
    pipe.valves = DummyValves(None, None, allow_missing_base=False)
    pipe.valves.ALLOW_MISSING_BASE_MODEL_FOR_DEBUG = flag_value

    llm_calls = 0

    async def _chat_completion(_: object, payload: dict[str, Any], __: object) -> dict[str, object]:
        del payload
        nonlocal llm_calls
        llm_calls += 1
        return {"ok": True}

    module.generate_chat_completion = _chat_completion
    module.preprocess_heuristic = lambda _text: {
        "outcome": "no_directive",
        "directive": None,
    }

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-missing-base-debug-truthy",
        )
    )

    assert result == (
        "Context Compiler debug mode: BASE_MODEL_ID is empty; skipping model passthrough."
    )
    assert llm_calls == 0


def test_preprocessor_pipe_supports_async_user_lookup(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_async_user_lookup", monkeypatch)
    pipe = module.Pipe()

    async def _get_user_by_id(user_id: object) -> dict[str, object]:
        return {"id": user_id}

    monkeypatch.setattr(module.Users, "get_user_by_id", _get_user_by_id)

    error = asyncio.run(
        pipe._validate_configured_model_ids(
            request=object(),
            user_payload={"id": "u1"},
            base_model_id="base-model",
            preprocessor_model_id="prep-model",
        )
    )

    assert error is None


def test_invalid_preprocessor_model_is_normalized(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_invalid", monkeypatch)
    pipe = module.Pipe()

    async def _models(_: object, user: object = None) -> list[dict[str, str]]:
        del user
        return [{"id": "base-model"}]

    module.get_all_models = _models

    error = asyncio.run(
        pipe._validate_configured_model_ids(
            request=object(),
            user_payload={"id": "u1"},
            base_model_id="base-model",
            preprocessor_model_id="missing-prep-model",
        )
    )

    assert error == (
        "Context Compiler pipe misconfigured: PREPROCESSOR_MODEL_ID was not found "
        "in Open WebUI models."
    )


def test_preprocessor_fallback_uses_preprocessor_model_only(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_routing", monkeypatch)
    pipe = module.Pipe()

    calls: list[str] = []

    async def _chat_completion(_: object, payload: dict[str, Any], __: object) -> dict[str, object]:
        calls.append(str(payload.get("model", "")))
        # First call is fallback preprocess completion; return no directive.
        # Second call is main forward passthrough.
        if len(calls) == 1:
            return {"choices": [{"message": {"content": "no_directive"}}]}
        return {"ok": True}

    async def _models(_: object, user: object = None) -> list[dict[str, str]]:
        del user
        return [{"id": "base-model"}, {"id": "prep-model"}, {"id": "pipe-model"}]

    def _heuristic(_: str) -> dict[str, object]:
        return {"outcome": "no_directive", "directive": None}

    module.generate_chat_completion = _chat_completion
    module.get_all_models = _models
    module.preprocess_heuristic = _heuristic

    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"

    body = {
        "model": "pipe-model",
        "messages": [{"role": "user", "content": "please use docker"}],
    }
    result = asyncio.run(
        pipe.pipe(
            body,
            __user__={"id": "u1"},
            __request__=object(),
        )
    )

    assert result == {"ok": True}
    assert calls == ["prep-model", "base-model"]


def test_preprocessor_fallback_rejects_premise_near_miss_rewrite(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_reject_premise_rewrite", monkeypatch)
    pipe = module.Pipe()

    async def _chat_completion(_: object, payload: dict[str, Any], __: object) -> dict[str, object]:
        del payload
        return {"choices": [{"message": {"content": "set premise concise replies"}}]}

    module.generate_chat_completion = _chat_completion
    module.render_prompt = lambda *_: "prompt"

    directive, error = asyncio.run(
        pipe._llm_fallback_preprocess(
            "set premise to concise replies",
            {"premise": None, "policies": {}, "version": 2},
            request=object(),
            user_payload={"id": "u1"},
            prompt_profile="default",
            model_id="prep-model",
        )
    )

    assert directive is None
    assert error is None


def test_recursion_guard_for_preprocessor_model(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_recursion", monkeypatch)
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "pipe-model"

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hi"}]},
            __user__={"id": "u1"},
            __request__=object(),
        )
    )

    assert result == (
        "Context Compiler pipe misconfigured: PREPROCESSOR_MODEL_ID must not "
        "match the selected pipe model id to avoid recursive routing."
    )


def test_pipe_normalizes_preprocessor_model_not_found_response(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_model_not_found_response", monkeypatch)
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"

    async def _chat_completion(_: object, payload: dict[str, Any], __: object) -> dict[str, object]:
        if payload.get("model") == "prep-model":
            return {"error": {"message": "model not found"}}
        return {"ok": True}

    module.generate_chat_completion = _chat_completion
    module.preprocess_heuristic = lambda _text: {"outcome": "no_directive", "directive": None}

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
        )
    )

    assert result == (
        "Context Compiler pipe misconfigured: PREPROCESSOR_MODEL_ID is invalid or "
        "not configured in Open WebUI. Configure a valid model id in "
        "Admin Panel → Settings → Models."
    )


def test_pipe_normalizes_preprocessor_model_not_found_exception(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs(
        "owui_preproc_model_not_found_exception", monkeypatch
    )
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"

    class _PreprocessorError(Exception):
        def __init__(self) -> None:
            super().__init__("preprocessor failed")
            self.detail = {"error": {"message": "model not found"}}

    async def _chat_completion(_: object, payload: dict[str, Any], __: object) -> dict[str, object]:
        if payload.get("model") == "prep-model":
            raise _PreprocessorError()
        return {"ok": True}

    module.generate_chat_completion = _chat_completion
    module.preprocess_heuristic = lambda _text: {"outcome": "no_directive", "directive": None}

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
        )
    )

    assert result == (
        "Context Compiler pipe misconfigured: PREPROCESSOR_MODEL_ID is invalid or "
        "not configured in Open WebUI. Configure a valid model id in "
        "Admin Panel → Settings → Models."
    )


def test_preprocessor_pipe_restore_and_persist_checkpoint_points(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_checkpoint", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY["chat-1"] = "ckpt-in"

    class _FakeEngine:
        def __init__(self, kind: str, checkpoint_out: str, *, has_pending: bool = False) -> None:
            self.kind = kind
            self.state = {"premise": None, "policies": {}, "version": 2}
            self.has_pending = has_pending
            self.imported: list[str] = []
            self._checkpoint_out = checkpoint_out
            self.export_calls = 0

        def import_checkpoint_json(self, payload: str) -> None:
            self.imported.append(payload)

        def export_checkpoint_json(self) -> str:
            self.export_calls += 1
            return self._checkpoint_out

        def export_checkpoint(self) -> dict[str, object]:
            pending: object = None
            if self.has_pending:
                pending = {
                    "kind": "replacement",
                    "replacement": {"kind": "use_only", "new_item": "kubectl", "old_item": None},
                    "prompt_to_user": "confirm?",
                }
            return {
                "checkpoint_version": 1,
                "authoritative_state": self.state,
                "pending": pending,
            }

        def has_pending_clarification(self) -> bool:
            return self.has_pending

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
    monkeypatch.setattr(module, "preprocess_heuristic", lambda _text: {"outcome": "no_directive"})
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda _value, **_kwargs: None)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
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


def test_preprocessor_pipe_normal_update_returns_local_ack_and_persists_checkpoint(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_update_forward", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    monkeypatch.setattr(
        module,
        "preprocess_heuristic",
        lambda text: (
            {
                "outcome": module.PREPROCESS_OUTCOME_DIRECTIVE,
                "directive": "remove policy peanuts",
            }
            if "remove policy peanuts" in text.lower()
            else {
                "outcome": module.PREPROCESS_OUTCOME_DIRECTIVE,
                "directive": "prohibit peanuts",
            }
        ),
    )
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda value, **_kwargs: value)

    forwarded_payloads: list[dict[str, object]] = []

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        forwarded_payloads.append(payload)
        return {"ok": True}

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    chat_key = "chat-preproc-update"

    result = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "please disallow peanuts"}],
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


def test_preprocessor_pipe_update_directives_return_local_ack_across_shapes(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_update_shapes", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    forwarded_payloads: list[dict[str, object]] = []

    async def _track_downstream(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        forwarded_payloads.append(payload)
        return {"ok": True}

    monkeypatch.setattr(module, "generate_chat_completion", _track_downstream)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"

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
                "messages": [{"role": "user", "content": "use docker instead of docker"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-replace-noop",
        )
    )
    assert result == "State updated: Use docker."
    assert len(forwarded_payloads) == 0


def test_preprocessor_pipe_show_state_returns_local_summary_and_bypasses_preprocess_and_model(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_show_state", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    downstream_calls = 0
    preprocess_calls = 0

    async def _track_downstream(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        del payload
        nonlocal downstream_calls
        downstream_calls += 1
        return {"choices": [{"message": {"content": "downstream"}}]}

    async def _track_preprocess(
        self, *args: object, **kwargs: object
    ) -> tuple[str | None, str | None]:
        del self, args, kwargs
        nonlocal preprocess_calls
        preprocess_calls += 1
        return None, None

    monkeypatch.setattr(module, "generate_chat_completion", _track_downstream)
    monkeypatch.setattr(module.Pipe, "_preprocess_user_input", _track_preprocess)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True
    chat_id = "chat-preproc-show-state"

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
    assert preprocess_calls == 0
    assert "Context Compiler trace" not in no_pending


def test_preprocessor_pipe_show_state_reports_pending_yes(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_show_state_pending", monkeypatch)
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
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "show state"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-preproc-show-state-pending",
        )
    )
    assert result == "Premise: none\nUse: none\nProhibit: none\nPending clarification: yes"


def test_preprocessor_pipe_show_state_non_exact_routes_normally(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_show_state_non_exact", monkeypatch)
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

    monkeypatch.setattr(module, "generate_chat_completion", _track_downstream)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"

    result = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "show state please"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-preproc-show-state-non-exact",
        )
    )
    assert result == {"choices": [{"message": {"content": "downstream"}}]}
    assert downstream_calls >= 1


def test_preprocessor_pipe_show_state_exact_match_is_case_insensitive_after_trim(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_show_state_case_trim", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    downstream_calls = 0
    preprocess_calls = 0

    async def _track_downstream(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        del payload
        nonlocal downstream_calls
        downstream_calls += 1
        return {"choices": [{"message": {"content": "downstream"}}]}

    async def _track_preprocess(
        self, *args: object, **kwargs: object
    ) -> tuple[str | None, str | None]:
        del self, args, kwargs
        nonlocal preprocess_calls
        preprocess_calls += 1
        return None, None

    monkeypatch.setattr(module, "generate_chat_completion", _track_downstream)
    monkeypatch.setattr(module.Pipe, "_preprocess_user_input", _track_preprocess)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "  ShOw StAtE  "}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-preproc-show-state-case-trim",
        )
    )

    assert result == "Premise: none\nUse: none\nProhibit: none\nPending clarification: no"
    assert downstream_calls == 0
    assert preprocess_calls == 0


@pytest.mark.parametrize(
    ("confirmation",),
    [
        ("yes",),
        ("no",),
    ],
)
def test_preprocessor_pipe_bypasses_preprocess_while_pending(
    monkeypatch, confirmation: str
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_pending_bypass", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    class _PendingEngine:
        def __init__(self) -> None:
            self.state = {"premise": None, "policies": {}, "version": 2}
            self.pending = True
            self.step_inputs: list[str] = []

        def export_checkpoint(self) -> dict[str, object]:
            pending: object = None
            if self.pending:
                pending = {
                    "kind": "replacement",
                    "replacement": {"kind": "use_only", "new_item": "kubectl", "old_item": None},
                    "prompt_to_user": "confirm?",
                }
            return {
                "checkpoint_version": 1,
                "authoritative_state": self.state,
                "pending": pending,
            }

        def has_pending_clarification(self) -> bool:
            return self.pending

        def export_checkpoint_json(self) -> str:
            return "ckpt-out"

        def step(self, text: str) -> dict[str, object]:
            self.step_inputs.append(text)
            if self.pending and text in {"yes", "no"}:
                self.pending = False
                return {"kind": "update", "state": self.state}
            if self.pending:
                return {"kind": "clarify", "state": None, "prompt_to_user": "confirm?"}
            return {"kind": "passthrough", "state": None}

    engine = _PendingEngine()
    monkeypatch.setattr(module, "create_engine", lambda: engine)

    def _fail_preprocess(_: str) -> dict[str, object]:
        raise AssertionError("should not preprocess")

    monkeypatch.setattr(module, "preprocess_heuristic", _fail_preprocess)

    forwarded_payloads: list[dict[str, Any]] = []

    async def _track_downstream_model(
        _: object, payload: dict[str, Any], __: object
    ) -> dict[str, object]:
        forwarded_payloads.append(payload)
        return {"ok": True}

    monkeypatch.setattr(module, "generate_chat_completion", _track_downstream_model)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": confirmation}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-pending",
        )
    )

    assert result == "State updated."
    assert engine.step_inputs == [confirmation]
    assert module._CHECKPOINTS_BY_CHAT_KEY["chat-pending"] == "ckpt-out"
    assert len(forwarded_payloads) == 0


@pytest.mark.parametrize(
    ("confirmation", "expected_policies"),
    [
        ("yes", {"kubectl": "use"}),
        ("no", {}),
    ],
)
def test_preprocessor_pipe_checkpoint_resume_yes_no_end_to_end(
    monkeypatch,
    confirmation: str,
    expected_policies: dict[str, str],
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_resume_e2e", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    heuristic_inputs: list[str] = []

    def _heuristic(text: str) -> dict[str, object]:
        if text in {"yes", "no"}:
            raise AssertionError("heuristic preprocess should be bypassed while pending")
        heuristic_inputs.append(text)
        return {"outcome": "no_directive", "directive": None}

    monkeypatch.setattr(module, "preprocess_heuristic", _heuristic)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"

    chat_key = "chat-resume-e2e"
    clarify = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "use kubectl instead of docker"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__=chat_key,
        )
    )
    assert isinstance(clarify, str)
    assert clarify == 'Did you mean to use "kubectl" instead?'
    assert heuristic_inputs == ["use kubectl instead of docker"]

    module._ENGINES_BY_CHAT_KEY.clear()

    forwarded_payloads: list[dict[str, Any]] = []

    async def _track_downstream_model(
        _: object, payload: dict[str, Any], __: object
    ) -> dict[str, object]:
        forwarded_payloads.append(payload)
        return {"ok": True}

    monkeypatch.setattr(module, "generate_chat_completion", _track_downstream_model)

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
    resumed_engine = cast(Any, module._ENGINES_BY_CHAT_KEY[chat_key])
    assert resumed_engine.state == {
        "premise": None,
        "policies": expected_policies,
        "version": 2,
    }
    resumed_checkpoint = json.loads(module._CHECKPOINTS_BY_CHAT_KEY[chat_key])
    assert resumed_checkpoint["pending"] is None
    assert len(forwarded_payloads) == 0


@pytest.mark.parametrize(
    ("user_input", "expected"),
    [
        (
            "use",
            "Policy item cannot be empty.\nUse 'use <item>' with a non-empty value.",
        ),
        (
            "prohibit",
            "Policy item cannot be empty.\nUse 'prohibit <item>' with a non-empty value.",
        ),
        (
            "remove policy",
            "Policy item cannot be empty.\nUse 'remove policy <item>' with a non-empty value.",
        ),
        (
            "use docker instead of",
            "Replacement requires both new and old items.\n"
            "Use 'use <new item> instead of <old item>' with non-empty values.",
        ),
        (
            "use instead of docker",
            "Replacement requires both new and old items.\n"
            "Use 'use <new item> instead of <old item>' with non-empty values.",
        ),
    ],
)
def test_preprocessor_pipe_skips_fallback_for_directive_shaped_malformed_inputs(
    monkeypatch,
    user_input: str,
    expected: str,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_skip_fallback_malformed", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    monkeypatch.setattr(
        module,
        "preprocess_heuristic",
        lambda _text: {"outcome": "no_directive", "directive": None},
    )

    fallback_calls = 0

    async def _fallback(
        self,
        message: str,
        state: dict[str, object],
        *,
        request: object,
        user_payload: dict[str, object],
        prompt_profile: str,
        model_id: str,
    ) -> tuple[str | None, str | None]:
        nonlocal fallback_calls
        del self, message, state, request, user_payload, prompt_profile, model_id
        fallback_calls += 1
        raise AssertionError("fallback should not be called for directive-shaped malformed input")

    downstream_calls = 0

    async def _downstream(_: object, payload: dict[str, Any], __: object) -> dict[str, object]:
        nonlocal downstream_calls
        downstream_calls += 1
        raise AssertionError(f"downstream model should not be called: {payload.get('model')}")

    monkeypatch.setattr(module.Pipe, "_llm_fallback_preprocess", _fallback)
    monkeypatch.setattr(module, "generate_chat_completion", _downstream)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": user_input}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-malformed",
        )
    )

    assert result == expected
    assert fallback_calls == 0
    assert downstream_calls == 0


def test_preprocessor_pipe_near_miss_directives_return_deterministic_clarify_without_model_calls(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_near_miss_clarify", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    monkeypatch.setattr(
        module,
        "preprocess_heuristic",
        lambda _text: {"outcome": "no_directive", "directive": None},
    )

    fallback_calls = 0

    async def _fallback(
        self,
        message: str,
        state: dict[str, object],
        *,
        request: object,
        user_payload: dict[str, object],
        prompt_profile: str,
        model_id: str,
    ) -> tuple[str | None, str | None]:
        nonlocal fallback_calls
        del self, message, state, request, user_payload, prompt_profile, model_id
        fallback_calls += 1
        raise AssertionError("fallback should not be called for near-miss directive input")

    downstream_calls = 0

    async def _downstream(_: object, payload: dict[str, Any], __: object) -> dict[str, object]:
        nonlocal downstream_calls
        downstream_calls += 1
        raise AssertionError(f"downstream model should not be called: {payload.get('model')}")

    monkeypatch.setattr(module.Pipe, "_llm_fallback_preprocess", _fallback)
    monkeypatch.setattr(module, "generate_chat_completion", _downstream)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"

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

    assert fallback_calls == 0
    assert downstream_calls == 0


@pytest.mark.parametrize(
    "user_input",
    [
        "ok. prohibit peanuts",
        "```\nuse docker\n```",
        "the command is `use docker`",
        'the docs say "use docker"',
        "can you use docker?",
    ],
)
def test_preprocessor_pipe_fallback_boundary_unsafe_sources_do_not_mutate_state(
    monkeypatch, user_input: str
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_fallback_boundary_unsafe", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    calls: list[str] = []

    async def _chat_completion(_: object, payload: dict[str, Any], __: object) -> dict[str, object]:
        model = str(payload.get("model", ""))
        calls.append(model)
        if model == "prep-model":
            return {"choices": [{"message": {"content": "use docker"}}]}
        return {"ok": True}

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)
    monkeypatch.setattr(module, "render_prompt", lambda *_args, **_kwargs: "prompt")
    monkeypatch.setattr(
        module,
        "preprocess_heuristic",
        lambda _text: {"outcome": "unknown", "directive": None, "rule_id": "test"},
    )

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"

    chat_id = "chat-fallback-boundary-unsafe"
    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": user_input}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__=chat_id,
        )
    )

    assert result == {"ok": True}
    assert calls == ["prep-model", "base-model"]
    assert chat_id in module._ENGINES_BY_CHAT_KEY
    assert module._ENGINES_BY_CHAT_KEY[chat_id].state["policies"] == {}


def test_preprocessor_pipe_trace_off_keeps_existing_response_shape(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_trace_off_shape", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    async def _chat_completion(_: object, payload: dict[str, Any], __: object) -> dict[str, object]:
        if payload.get("model") == "prep-model":
            return {"choices": [{"message": {"content": "no_directive"}}]}
        return {"choices": [{"message": {"content": "downstream"}}]}

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)
    monkeypatch.setattr(module, "preprocess_heuristic", lambda _text: {"outcome": "no_directive"})
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda _value, **_kwargs: None)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = False

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-preproc-trace-off",
        )
    )
    assert result == {"choices": [{"message": {"content": "downstream"}}]}


def test_preprocessor_pipe_trace_on_appends_trace_to_user_visible_output(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_trace_on", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    async def _chat_completion(_: object, payload: dict[str, Any], __: object) -> dict[str, object]:
        del payload
        return {"choices": [{"message": {"content": "downstream"}}]}

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)
    monkeypatch.setattr(
        module,
        "preprocess_heuristic",
        lambda _text: {
            "outcome": module.PREPROCESS_OUTCOME_DIRECTIVE,
            "directive": "prohibit peanuts",
        },
    )
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda value, **_kwargs: value)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "please use docker"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-preproc-trace-on",
        )
    )
    assert isinstance(result, str)
    content = result
    assert content.startswith("State updated: Prohibit peanuts.")
    assert "Context Compiler trace" in content
    assert "decision kind: update" in content
    assert "preprocessor output:" not in content
    assert "downstream LLM call: no" in content
    assert "state change:" in content
    assert "active state:" in content
    assert "state injected: no" in content
    assert "\n\nstate injected: no" in content


def test_preprocessor_pipe_trace_on_passthrough_appends_trace_to_llm_content(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_trace_on_passthrough", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    async def _chat_completion(_: object, payload: dict[str, Any], __: object) -> dict[str, object]:
        if payload.get("model") == "prep-model":
            return {"choices": [{"message": {"content": "no_directive"}}]}
        return {"choices": [{"message": {"content": "downstream"}}]}

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)
    monkeypatch.setattr(module, "preprocess_heuristic", lambda _text: {"outcome": "no_directive"})
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda _value, **_kwargs: None)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-preproc-trace-on-passthrough",
        )
    )
    content = result["choices"][0]["message"]["content"]
    assert "downstream" in content
    assert "Context Compiler trace" in content
    assert "decision kind: passthrough" in content
    assert "downstream LLM call: yes" in content
    assert "active state:" in content
    assert "state injected: no" in content


def test_preprocessor_pipe_trace_on_passthrough_stream_appends_trace_after_chunks(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_trace_on_stream", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    async def _streaming_response() -> Any:
        for part in ("down", "stream"):
            yield part

    async def _chat_completion(_: object, payload: dict[str, Any], __: object) -> Any:
        if payload.get("model") == "prep-model":
            return {"choices": [{"message": {"content": "no_directive"}}]}
        return _streaming_response()

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)
    monkeypatch.setattr(module, "preprocess_heuristic", lambda _text: {"outcome": "no_directive"})
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda _value, **_kwargs: None)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True

    result = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-preproc-trace-on-stream",
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


def test_preprocessor_pipe_trace_on_clarify_shows_prompt_and_no_downstream_call(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_trace_clarify", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    monkeypatch.setattr(
        module,
        "preprocess_heuristic",
        lambda _text: {"outcome": "no_directive", "directive": None},
    )

    downstream_calls = 0

    async def _downstream(_: object, payload: dict[str, Any], __: object) -> dict[str, object]:
        nonlocal downstream_calls
        downstream_calls += 1
        del payload
        return {"choices": [{"message": {"content": "downstream"}}]}

    monkeypatch.setattr(module, "generate_chat_completion", _downstream)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True

    result = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "set premise to concise answers"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-preproc-trace-clarify",
        )
    )
    assert isinstance(result, str)
    assert "decision kind: clarify" in result
    assert "active state:" in result
    assert "clarification prompt:" in result
    assert "downstream LLM call: no" in result
    assert "state injected: no" in result
    assert downstream_calls == 0


def test_preprocessor_pipe_trace_appends_on_object_response_for_passthrough_and_update(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_trace_object_response", monkeypatch)
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

    def _heuristic(text: str) -> dict[str, object]:
        if "use docker" in text.lower():
            return {"outcome": module.PREPROCESS_OUTCOME_DIRECTIVE, "directive": "use docker"}
        return {"outcome": "no_directive", "directive": None}

    monkeypatch.setattr(module, "preprocess_heuristic", _heuristic)
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda value, **_kwargs: value)

    forwarded_payloads: list[dict[str, object]] = []

    async def _chat_completion(_: object, payload: dict[str, object], __: object) -> object:
        forwarded_payloads.append(payload)
        return _Response("downstream")

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True

    passthrough = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-preproc-object-passthrough",
        )
    )
    passthrough_content = passthrough.choices[0].message.content
    assert "Context Compiler trace" in passthrough_content
    assert "decision kind: passthrough" in passthrough_content
    assert "downstream LLM call: yes" in passthrough_content

    update = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "use docker"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-preproc-object-update",
        )
    )
    assert isinstance(update, str)
    update_content = update
    assert "Context Compiler trace" in update_content
    assert "decision kind: update" in update_content
    assert "downstream LLM call: no" in update_content
    assert "state injected: no" in update_content
    assert len(forwarded_payloads) == 2


def test_preprocessor_pipe_trace_appends_on_streaming_response_wrapper_passthrough_and_update(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_trace_streaming_wrapper", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    class _StreamingResponse:
        def __init__(self, parts: tuple[str, ...]) -> None:
            async def _iter() -> object:
                for part in parts:
                    yield part

            self.body_iterator = _iter()

    def _heuristic(text: str) -> dict[str, object]:
        if "use docker" in text.lower():
            return {"outcome": module.PREPROCESS_OUTCOME_DIRECTIVE, "directive": "use docker"}
        return {"outcome": "no_directive", "directive": None}

    monkeypatch.setattr(module, "preprocess_heuristic", _heuristic)
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda value, **_kwargs: value)

    forwarded_payloads: list[dict[str, object]] = []

    async def _chat_completion(_: object, payload: dict[str, object], __: object) -> object:
        forwarded_payloads.append(payload)
        return _StreamingResponse(("data: stub\n\n", "data: [DONE]\n\n"))

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True

    passthrough = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-preproc-stream-wrapper-passthrough",
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
            __chat_id__="chat-preproc-stream-wrapper-update",
        )
    )
    assert isinstance(update, str)
    assert "Context Compiler trace" in update
    assert "decision kind: update" in update
    assert "state injected: no" in update
    assert len(forwarded_payloads) == 2


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
def test_preprocessor_pipe_trace_update_clear_reset_paths_single_and_consistent(
    monkeypatch,
    steps: list[str],
    expected_ack: str,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_trace_clear_reset", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    monkeypatch.setattr(
        module,
        "preprocess_heuristic",
        lambda _text: {"outcome": "no_directive", "directive": None},
    )
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda _value, **_kwargs: None)

    downstream_calls = 0

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        nonlocal downstream_calls
        if payload.get("model") == "prep-model":
            return {"choices": [{"message": {"content": "no_directive"}}]}
        downstream_calls += 1
        return {"choices": [{"message": {"content": "downstream"}}]}

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True

    result: object = ""
    for idx, user_input in enumerate(steps):
        result = asyncio.run(
            pipe.pipe(
                {"model": "pipe-model", "messages": [{"role": "user", "content": user_input}]},
                __user__={"id": "u1"},
                __request__=object(),
                __chat_id__=f"chat-preproc-trace-clear-reset-{hash(tuple(steps))}",
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


def test_preprocessor_pipe_clear_state_trace_not_duplicated_when_model_echoes_history(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_trace_echo_dedupe", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    monkeypatch.setattr(
        module,
        "preprocess_heuristic",
        lambda _text: {"outcome": "no_directive", "directive": None},
    )
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda _value, **_kwargs: None)

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

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True
    chat_id = "chat-preproc-trace-echo-dedupe"

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


def test_preprocessor_pipe_clear_state_strips_preexisting_contradictory_trace_from_model_output(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs(
        "owui_preproc_trace_strip_contradiction", monkeypatch
    )
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    monkeypatch.setattr(
        module,
        "preprocess_heuristic",
        lambda _text: {"outcome": "no_directive", "directive": None},
    )
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda _value, **_kwargs: None)

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

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True
    chat_id = "chat-preproc-trace-strip-contradiction"

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


def test_preprocessor_pipe_update_trace_local_ack_when_heuristic_emits_directive(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_nl_use_docker", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    monkeypatch.setattr(
        module,
        "preprocess_heuristic",
        lambda text: (
            {"outcome": module.PREPROCESS_OUTCOME_DIRECTIVE, "directive": "use docker"}
            if "i think we should use docker" in text.lower()
            else {"outcome": "no_directive", "directive": None}
        ),
    )
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda value, **_kwargs: value)

    forwarded_payloads: list[dict[str, object]] = []

    async def _chat_completion(
        _: object,
        payload: dict[str, object],
        __: object,
    ) -> dict[str, object]:
        forwarded_payloads.append(payload)
        return {"choices": [{"message": {"content": "downstream"}}]}

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True

    result = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "i think we should use docker"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-preproc-nl-use-docker",
        )
    )
    assert isinstance(result, str)
    content = result
    assert content.count("Context Compiler trace") == 1
    assert "decision kind: update" in content
    assert "downstream LLM call: no" in content
    assert "downstream LLM call: yes" not in content
    assert "active state: use docker" in content
    assert "state injected: no" in content
    assert len(forwarded_payloads) == 0


def test_preprocessor_pipe_replacement_update_trace_local_ack_when_heuristic_emits_directive(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_nl_replace", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    monkeypatch.setattr(
        module,
        "preprocess_heuristic",
        lambda text: (
            {"outcome": module.PREPROCESS_OUTCOME_DIRECTIVE, "directive": "use docker"}
            if text.strip().lower() == "use docker"
            else (
                {
                    "outcome": module.PREPROCESS_OUTCOME_DIRECTIVE,
                    "directive": "use podman instead of docker",
                }
                if "switch to podman instead of docker" in text.lower()
                else {"outcome": "no_directive", "directive": None}
            )
        ),
    )
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda value, **_kwargs: value)

    async def _chat_completion(
        _: object,
        payload: dict[str, object],
        __: object,
    ) -> dict[str, object]:
        del payload
        return {"choices": [{"message": {"content": "downstream"}}]}

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True
    chat_id = "chat-preproc-nl-replace"

    _ = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "use docker"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__=chat_id,
        )
    )

    result = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "switch to podman instead of docker"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__=chat_id,
        )
    )
    assert isinstance(result, str)
    content = result
    assert content.count("Context Compiler trace") == 1
    assert "decision kind: update" in content
    assert "downstream LLM call: no" in content
    assert "downstream LLM call: yes" not in content
    assert "active state: use podman" in content
    assert "state injected: no" in content


def test_preprocessor_pipe_ambiguous_text_passthrough_trace_streaming(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs(
        "owui_preproc_ambiguous_passthrough_stream", monkeypatch
    )
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    monkeypatch.setattr(module, "preprocess_heuristic", lambda _text: {"outcome": "no_directive"})
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda _value, **_kwargs: None)

    class _StreamingResponse:
        def __init__(self) -> None:
            async def _iter() -> object:
                for part in ("data: downstream\n\n", "data: [DONE]\n\n"):
                    yield part

            self.body_iterator = _iter()

    async def _chat_completion(_: object, payload: dict[str, object], __: object) -> object:
        if payload.get("model") == "prep-model":
            return {"choices": [{"message": {"content": "no_directive"}}]}
        return _StreamingResponse()

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True

    result = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "docker is interesting"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-preproc-ambiguous-stream",
        )
    )

    async def _collect_stream(wrapper: object) -> str:
        parts: list[str] = []
        async for chunk in wrapper.body_iterator:
            assert isinstance(chunk, str)
            parts.append(chunk)
        return "".join(parts)

    content = asyncio.run(_collect_stream(result))
    assert content.count("Context Compiler trace") == 1
    assert "decision kind: passthrough" in content
    assert "downstream LLM call: yes" in content
    assert "downstream LLM call: no" not in content
    assert "state injected: no" in content


def test_preprocessor_pipe_natural_language_abstention_can_passthrough_with_trace(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_nl_abstention", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    # Use the real heuristic behavior for this phrase (unknown/no_directive),
    # and force fallback to abstain so runtime stays conservative.
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda _value, **_kwargs: None)

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        if payload.get("model") == "prep-model":
            return {"choices": [{"message": {"content": "no_directive"}}]}
        return {"choices": [{"message": {"content": "downstream"}}]}

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True

    result = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "i think we should use docker"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-preproc-nl-abstention",
        )
    )
    assert isinstance(result, dict)
    content = result["choices"][0]["message"]["content"]
    assert content.count("Context Compiler trace") == 1
    assert "decision kind: passthrough" in content
    assert "active state: none" in content
    assert "downstream LLM call: yes" in content
    assert "state injected: no" in content


def test_preprocessor_pipe_pending_clarification_bypasses_preprocessing_for_ambiguous_yes(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_pending_yeah_probably", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    heuristic_calls: list[str] = []

    def _heuristic(text: str) -> dict[str, object]:
        if text.strip().lower() == "yeah probably":
            raise AssertionError("heuristic preprocess should be bypassed while pending")
        heuristic_calls.append(text)
        if "use podman instead of kubectl" in text.lower():
            return {
                "outcome": module.PREPROCESS_OUTCOME_DIRECTIVE,
                "directive": "use podman instead of kubectl",
            }
        return {"outcome": "no_directive", "directive": None}

    monkeypatch.setattr(module, "preprocess_heuristic", _heuristic)
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda value, **_kwargs: value)

    downstream_calls = 0

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        nonlocal downstream_calls
        downstream_calls += 1
        del payload
        return {"choices": [{"message": {"content": "downstream"}}]}

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True
    chat_id = "chat-preproc-pending-yeah-probably"

    first = asyncio.run(
        pipe.pipe(
            {
                "model": "pipe-model",
                "messages": [{"role": "user", "content": "use podman instead of kubectl"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__=chat_id,
        )
    )
    assert isinstance(first, str)
    assert first.count("Context Compiler trace") == 1
    assert "decision kind: clarify" in first
    assert "downstream LLM call: no" in first
    assert "state injected: no" in first

    second = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "yeah probably"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__=chat_id,
        )
    )
    assert isinstance(second, str)
    assert second.count("Context Compiler trace") == 1
    assert "decision kind: clarify" in second
    assert "downstream LLM call: no" in second
    assert "downstream LLM call: yes" not in second
    assert "state injected: no" in second
    assert downstream_calls == 0
    assert heuristic_calls == ["use podman instead of kubectl"]


def test_preprocessor_pipe_passthrough_injects_active_state_and_trace_reports_yes(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs(
        "owui_preproc_passthrough_state_injection", monkeypatch
    )
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    monkeypatch.setattr(
        module,
        "preprocess_heuristic",
        lambda text: (
            {"outcome": module.PREPROCESS_OUTCOME_DIRECTIVE, "directive": "use docker"}
            if text.strip().lower() == "use docker"
            else {"outcome": "no_directive", "directive": None}
        ),
    )
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda value, **_kwargs: value)

    forwarded_payloads: list[dict[str, object]] = []

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        forwarded_payloads.append(payload)
        return {"choices": [{"message": {"content": "answer"}}]}

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True
    chat_id = "chat-preproc-passthrough-injected-state"

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
    assert len(forwarded_payloads) == 2
    messages = forwarded_payloads[-1]["messages"]
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


def test_preprocessor_pipe_empty_state_passthrough_does_not_inject_and_trace_reports_no(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_empty_state_passthrough", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()
    monkeypatch.setattr(module, "preprocess_heuristic", lambda _text: {"outcome": "no_directive"})
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda _value, **_kwargs: None)

    forwarded_payloads: list[dict[str, object]] = []

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        forwarded_payloads.append(payload)
        return {"choices": [{"message": {"content": "answer"}}]}

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    pipe.valves.SHOW_CONTEXT_COMPILER_TRACE = True

    passthrough = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "hello"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-preproc-empty-state-passthrough",
        )
    )
    assert isinstance(passthrough, dict)
    assert len(forwarded_payloads) == 2
    messages = forwarded_payloads[-1]["messages"]
    assert isinstance(messages, list)
    assert not any(
        isinstance(msg, dict)
        and msg.get("role") == "system"
        and isinstance(msg.get("content"), str)
        and msg["content"].startswith("[[cc_state]]")
        for msg in messages
    )
    content = passthrough["choices"][0]["message"]["content"]
    assert "downstream LLM call: yes" in content
    assert "state injected: no" in content


def test_preprocessor_pipe_repeated_passthrough_does_not_duplicate_compiler_state_prompt(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs(
        "owui_preproc_repeated_passthrough_no_dup", monkeypatch
    )
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()
    monkeypatch.setattr(
        module,
        "preprocess_heuristic",
        lambda text: (
            {"outcome": module.PREPROCESS_OUTCOME_DIRECTIVE, "directive": "use docker"}
            if text.strip().lower() == "use docker"
            else {"outcome": "no_directive", "directive": None}
        ),
    )
    monkeypatch.setattr(module, "parse_preprocessor_output", lambda value, **_kwargs: value)

    forwarded_payloads: list[dict[str, object]] = []

    async def _chat_completion(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        forwarded_payloads.append(payload)
        return {"choices": [{"message": {"content": "answer"}}]}

    monkeypatch.setattr(module, "generate_chat_completion", _chat_completion)

    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"
    chat_id = "chat-preproc-repeated-passthrough-no-dup"

    _ = asyncio.run(
        pipe.pipe(
            {"model": "pipe-model", "messages": [{"role": "user", "content": "use docker"}]},
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__=chat_id,
        )
    )
    for idx in range(2):
        _ = asyncio.run(
            pipe.pipe(
                {
                    "model": "pipe-model",
                    "messages": [{"role": "user", "content": f"question {idx}"}],
                },
                __user__={"id": "u1"},
                __request__=object(),
                __chat_id__=chat_id,
            )
        )

    assert len(forwarded_payloads) == 4
    passthrough_payloads = [forwarded_payloads[1], forwarded_payloads[3]]
    for payload in passthrough_payloads:
        messages = payload.get("messages")
        assert isinstance(messages, list)
        cc_messages = [
            msg
            for msg in messages
            if isinstance(msg, dict)
            and msg.get("role") == "system"
            and isinstance(msg.get("content"), str)
            and msg["content"].startswith("[[cc_state]]")
        ]
        assert len(cc_messages) == 1


def test_preprocessor_pipe_frontmatter_title_and_public_symbol_stability(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_frontmatter_title", monkeypatch)
    assert "title: Context Compiler Pipe (Preprocessor)" in (module.__doc__ or "")
    assert hasattr(module, "Pipe")
