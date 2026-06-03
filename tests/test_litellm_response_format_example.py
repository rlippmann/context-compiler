import importlib.util
from pathlib import Path
from typing import Any

from context_compiler import create_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PATH = REPO_ROOT / "examples" / "integrations" / "litellm" / "response_format.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("litellm_response_format_example", EXAMPLE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_supported_policy_selects_no_response_format() -> None:
    module = _load_module()
    engine = create_engine()

    plan = module.plan_turn("hello", engine)
    assert plan["decision_kind"] == "passthrough"
    assert plan["selected_response_format_item"] is None
    assert plan["response_format"] is None


def test_use_compact_summary_selects_compact_summary_response_format() -> None:
    module = _load_module()
    engine = create_engine()

    assert engine.step("use compact_summary")["kind"] == "update"

    plan = module.plan_turn("summarize this", engine)
    assert plan["selected_response_format_item"] == "compact_summary"
    assert plan["response_format"] == module.COMPACT_SUMMARY_RESPONSE_FORMAT


def test_use_action_plan_selects_action_plan_response_format() -> None:
    module = _load_module()
    engine = create_engine()

    assert engine.step("use action_plan")["kind"] == "update"

    plan = module.plan_turn("what should i do next?", engine)
    assert plan["selected_response_format_item"] == "action_plan"
    assert plan["response_format"] == module.ACTION_PLAN_RESPONSE_FORMAT


def test_prohibit_compact_summary_omits_compact_summary_response_format() -> None:
    module = _load_module()
    engine = create_engine()

    assert engine.step("prohibit compact_summary")["kind"] == "update"

    plan = module.plan_turn("summarize this", engine)
    assert plan["selected_response_format_item"] is None
    assert plan["response_format"] is None


def test_contradiction_path_returns_clarify_and_skips_response_format() -> None:
    module = _load_module()
    engine = create_engine()

    assert engine.step("use compact_summary")["kind"] == "update"

    plan = module.plan_turn("prohibit compact_summary", engine)
    assert plan["decision_kind"] == "clarify"
    assert plan["clarify_prompt"] is not None
    assert plan["selected_response_format_item"] is None
    assert plan["response_format"] is None


def test_optional_litellm_call_includes_response_format_when_selected(monkeypatch) -> None:
    module = _load_module()
    seen: dict[str, object] = {}

    def _completion(**kwargs: Any) -> dict[str, object]:
        seen.update(kwargs)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setattr(module, "_get_litellm_completion", lambda: _completion)

    result = module.optional_litellm_call(
        user_input="summarize this",
        response_format=module.COMPACT_SUMMARY_RESPONSE_FORMAT,
    )

    assert result == "ok"
    assert seen["response_format"] == module.COMPACT_SUMMARY_RESPONSE_FORMAT


def test_optional_litellm_call_omits_response_format_when_not_selected(monkeypatch) -> None:
    module = _load_module()
    seen: dict[str, object] = {}

    def _completion(**kwargs: Any) -> dict[str, object]:
        seen.update(kwargs)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setattr(module, "_get_litellm_completion", lambda: _completion)

    result = module.optional_litellm_call(
        user_input="hello",
        response_format=None,
    )

    assert result == "ok"
    assert "response_format" not in seen
