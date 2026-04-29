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
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = ""

    assert pipe._resolve_preprocessor_model_id("base-model") == "base-model"


def test_pipe_requires_base_model_id_when_debug_disabled(monkeypatch) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_requires_base", monkeypatch)
    pipe = module.Pipe()
    pipe.valves.BASE_MODEL_ID = ""
    pipe.valves.ALLOW_MISSING_BASE_MODEL_FOR_DEBUG = False

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
    pipe.valves.BASE_MODEL_ID = "base-model"
    pipe.valves.PREPROCESSOR_MODEL_ID = "prep-model"

    assert pipe._resolve_preprocessor_model_id("base-model") == "prep-model"


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
        # First call is fallback precompile completion; return no directive.
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
    module.precompile_heuristic = _heuristic

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
        pipe._llm_fallback_precompile(
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
    module.precompile_heuristic = lambda _text: {"outcome": "no_directive", "directive": None}

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
    module.precompile_heuristic = lambda _text: {"outcome": "no_directive", "directive": None}

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
    monkeypatch.setattr(module, "precompile_heuristic", lambda _text: {"outcome": "no_directive"})
    monkeypatch.setattr(module, "parse_precompiler_output", lambda _value, **_kwargs: None)

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


def test_preprocessor_pipe_normal_update_returns_deterministic_ack_and_persists_checkpoint(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_update_forward", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    monkeypatch.setattr(
        module,
        "precompile_heuristic",
        lambda text: (
            {
                "outcome": module.PRECOMPILE_OUTCOME_DIRECTIVE,
                "directive": "remove policy peanuts",
            }
            if "remove policy peanuts" in text.lower()
            else {
                "outcome": module.PRECOMPILE_OUTCOME_DIRECTIVE,
                "directive": "prohibit peanuts",
            }
        ),
    )
    monkeypatch.setattr(module, "parse_precompiler_output", lambda value, **_kwargs: value)

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


def test_preprocessor_pipe_literal_replacement_update_summary_uses_new_item_only(
    monkeypatch,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_literal_replace_summary", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    downstream_calls = 0

    async def _track_downstream(
        _: object, payload: dict[str, object], __: object
    ) -> dict[str, object]:
        nonlocal downstream_calls
        downstream_calls += 1
        raise AssertionError(f"downstream model should not be called: {payload.get('model')}")

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
                "messages": [{"role": "user", "content": "use docker instead of docker"}],
            },
            __user__={"id": "u1"},
            __request__=object(),
            __chat_id__="chat-replace-noop",
        )
    )
    assert result == "State updated: Use docker."
    assert downstream_calls == 0


@pytest.mark.parametrize(
    ("confirmation", "expected_response"),
    [
        ("yes", "State updated: Use kubectl."),
        ("no", "State unchanged."),
    ],
)
def test_preprocessor_pipe_bypasses_precompile_while_pending(
    monkeypatch, confirmation: str, expected_response: str
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

    def _fail_precompile(_: str) -> dict[str, object]:
        raise AssertionError("should not precompile")

    monkeypatch.setattr(module, "precompile_heuristic", _fail_precompile)

    async def _fail_downstream_model(
        _: object, payload: dict[str, Any], __: object
    ) -> dict[str, object]:
        raise AssertionError(f"downstream model should not be called: {payload.get('model')}")

    monkeypatch.setattr(module, "generate_chat_completion", _fail_downstream_model)

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

    assert result == expected_response
    assert engine.step_inputs == [confirmation]
    assert module._CHECKPOINTS_BY_CHAT_KEY["chat-pending"] == "ckpt-out"


@pytest.mark.parametrize(
    ("confirmation", "expected_policies", "expected_response"),
    [
        ("yes", {"kubectl": "use"}, "State updated: Use kubectl."),
        ("no", {}, "State unchanged."),
    ],
)
def test_preprocessor_pipe_checkpoint_resume_yes_no_end_to_end(
    monkeypatch,
    confirmation: str,
    expected_policies: dict[str, str],
    expected_response: str,
) -> None:
    module = _load_module_with_openwebui_stubs("owui_preproc_resume_e2e", monkeypatch)
    module._ENGINES_BY_CHAT_KEY.clear()
    module._CHECKPOINTS_BY_CHAT_KEY.clear()

    heuristic_inputs: list[str] = []

    def _heuristic(text: str) -> dict[str, object]:
        if text in {"yes", "no"}:
            raise AssertionError("heuristic precompile should be bypassed while pending")
        heuristic_inputs.append(text)
        return {"outcome": "no_directive", "directive": None}

    monkeypatch.setattr(module, "precompile_heuristic", _heuristic)

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

    async def _fail_downstream_model(
        _: object, payload: dict[str, Any], __: object
    ) -> dict[str, object]:
        raise AssertionError(f"downstream model should not be called: {payload.get('model')}")

    monkeypatch.setattr(module, "generate_chat_completion", _fail_downstream_model)

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
    resumed_engine = cast(Any, module._ENGINES_BY_CHAT_KEY[chat_key])
    assert resumed_engine.state == {
        "premise": None,
        "policies": expected_policies,
        "version": 2,
    }
    resumed_checkpoint = json.loads(module._CHECKPOINTS_BY_CHAT_KEY[chat_key])
    assert resumed_checkpoint["pending"] is None
