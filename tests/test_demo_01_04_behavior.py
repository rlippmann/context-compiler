import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from demos.common import consume_last_report  # noqa: E402


def _load_demo_module(filename: str) -> ModuleType:
    module_name = f"test_demo_behavior_{filename[:-3]}"
    module_path = REPO_ROOT / "demos" / filename
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sequenced_outputs(outputs: list[str]) -> Callable[[object], str]:
    queue = list(outputs)

    def _fake_complete_messages(_messages: object) -> str:
        if not queue:
            raise AssertionError("No mocked LLM output remaining for this call.")
        return queue.pop(0)

    return _fake_complete_messages


def test_demo_01_reports_host_clarification_gate(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_demo_module("01_llm_contradiction_clarify.py")
    monkeypatch.setattr(
        module,
        "complete_messages",
        _sequenced_outputs(["ACTION:proceed\nI will continue."]),
    )

    module.main()
    output = capsys.readouterr().out
    report = consume_last_report()

    assert report is not None
    assert report["name"].startswith("01_contradiction_block")
    assert report["baseline_pass"] is False
    assert report["compiler_pass"] is True
    assert report["compiler_compact_pass"] is True
    assert report["demo_pass"] is True
    assert "baseline: FAIL" in output
    assert "compiler: PASS" in output
    assert "compiler+compact: PASS" in output


def test_demo_01_calls_llm_when_second_turn_is_not_clarify(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_demo_module("01_llm_contradiction_clarify.py")
    call_count = 0

    class _FakeEngine:
        def __init__(self) -> None:
            self.state = {"premise": None, "policies": {}, "version": 2}
            self._step_count = 0

        def step(self, _text: str) -> dict[str, str]:
            self._step_count += 1
            if self._step_count == 1:
                return {"kind": "update"}
            return {"kind": "passthrough"}

    def fake_complete_messages(_messages: object) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "ACTION:proceed"
        return "ACTION:clarify"

    monkeypatch.setattr(module, "create_engine", _FakeEngine)
    monkeypatch.setattr(module, "complete_messages", fake_complete_messages)

    module.main()
    output = capsys.readouterr().out
    report = consume_last_report()

    assert report is not None
    assert report["compiler_pass"] is False
    assert call_count == 2
    assert "compiler: FAIL" in output


def test_demo_01_baseline_and_compiler_use_intentionally_different_gates(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_demo_module("01_llm_contradiction_clarify.py")

    class _FakeEngine:
        def __init__(self) -> None:
            self.state = {"premise": None, "policies": {}, "version": 2}
            self._step_count = 0

        def step(self, _text: str) -> dict[str, str]:
            self._step_count += 1
            if self._step_count == 1:
                return {"kind": "update"}
            return {"kind": "passthrough"}

    monkeypatch.setattr(module, "create_engine", _FakeEngine)
    monkeypatch.setattr(
        module,
        "complete_messages",
        _sequenced_outputs(
            [
                "ACTION:clarify",
                "ACTION:proceed",
                "ACTION:proceed",
            ]
        ),
    )

    module.main()
    output = capsys.readouterr().out
    report = consume_last_report()

    assert report is not None
    assert report["baseline_pass"] is True
    assert report["compiler_pass"] is False
    assert report["compiler_compact_pass"] is True
    assert "baseline: PASS" in output
    assert "compiler: FAIL" in output


def test_demo_02_reports_persistent_prohibition(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_demo_module("02_llm_constraint_guardrail.py")
    monkeypatch.setattr(
        module,
        "complete_messages",
        _sequenced_outputs(
            [
                "Ingredients:\n- peanuts\n- coconut milk\nSteps:\n1. Cook peanuts.",
                (
                    "I cannot provide a peanut recipe because it conflicts with policy.\n"
                    "Try peanut-free curry with chickpeas."
                ),
                (
                    "I will not provide peanuts.\n"
                    "Use a peanut-free curry recipe with chickpeas instead."
                ),
            ]
        ),
    )

    module.main()
    output = capsys.readouterr().out
    report = consume_last_report()

    assert report is not None
    assert report["name"].startswith("02_constraint_drift")
    assert report["baseline_pass"] is False
    assert report["compiler_pass"] is True
    assert report["compiler_compact_pass"] is True
    assert report["demo_pass"] is True
    assert "baseline: FAIL" in output
    assert "compiler: PASS" in output
    assert "compiler+compact: PASS" in output


def test_demo_02_accepts_safe_alternative_without_explicit_refusal_phrase(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_demo_module("02_llm_constraint_guardrail.py")
    monkeypatch.setattr(
        module,
        "complete_messages",
        _sequenced_outputs(
            [
                "Ingredients:\n- peanuts\n- coconut milk\nSteps:\n1. Cook peanuts.",
                "Here is a peanut-free curry alternative with chickpeas and coconut milk.",
                "Use a peanut-free curry recipe with chickpeas instead.",
            ]
        ),
    )

    module.main()
    output = capsys.readouterr().out
    report = consume_last_report()

    assert report is not None
    assert report["name"].startswith("02_constraint_drift")
    assert report["baseline_pass"] is False
    assert report["compiler_pass"] is True
    assert report["compiler_compact_pass"] is True
    assert report["demo_pass"] is True
    assert "compiler: PASS" in output


def test_demo_02_uses_same_prohibited_content_check_for_baseline_and_compiler(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_demo_module("02_llm_constraint_guardrail.py")
    safe_response = "Use a peanut-free curry recipe with chickpeas instead."
    monkeypatch.setattr(
        module,
        "complete_messages",
        _sequenced_outputs([safe_response, safe_response, safe_response]),
    )

    module.main()
    output = capsys.readouterr().out
    report = consume_last_report()

    assert report is not None
    assert report["baseline_pass"] is True
    assert report["compiler_pass"] is True
    assert report["compiler_compact_pass"] is True
    assert "baseline: PASS" in output
    assert "compiler: PASS" in output


def test_demo_02_compact_clarify_branch_skips_compact_llm_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_demo_module("02_llm_constraint_guardrail.py")
    calls: list[object] = []

    def fake_complete_messages(messages: object) -> str:
        calls.append(messages)
        if len(calls) == 1:
            return "Ingredients:\n- peanuts\nSteps:\n1. Cook peanuts."
        return "I cannot provide peanuts; conflicts with policy. Try chickpea curry."

    monkeypatch.setattr(module, "complete_messages", fake_complete_messages)
    monkeypatch.setattr(
        module,
        "compact_user_turns",
        lambda turns: ([], {"premise": None, "policies": {}, "version": 2}, "Need clarification."),
    )

    module.main()
    output = capsys.readouterr().out
    report = consume_last_report()

    assert report is not None
    assert len(calls) == 2
    assert report["compiler_compact_pass"] is True
    assert "compiler+compact: PASS" in output


def test_demo_03_reports_explicit_premise_change(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_demo_module("03_llm_premise_guardrail.py")
    monkeypatch.setattr(
        module,
        "complete_messages",
        _sequenced_outputs(
            [
                "PREMISE: vegetarian curry\nPlan:\n- vegetarian shopping list",
                "PREMISE: vegan curry\nPlan:\n- vegan shopping list",
                "PREMISE: vegan curry\nPlan:\n- vegan ingredients only",
            ]
        ),
    )

    module.main()
    output = capsys.readouterr().out
    report = consume_last_report()

    assert report is not None
    assert report["name"].startswith("03_explicit_premise_change")
    assert report["baseline_pass"] is False
    assert report["compiler_pass"] is True
    assert report["compiler_compact_pass"] is True
    assert report["demo_pass"] is True
    assert "baseline: FAIL" in output
    assert "compiler: PASS" in output
    assert "compiler+compact: PASS" in output


def test_demo_03_compact_clarify_branch_reports_compact_fail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_demo_module("03_llm_premise_guardrail.py")
    calls: list[object] = []

    def fake_complete_messages(messages: object) -> str:
        calls.append(messages)
        if len(calls) == 1:
            return "PREMISE: vegetarian curry\nPlan:\n- vegetarian ingredients"
        return "PREMISE: vegan curry\nPlan:\n- vegan ingredients"

    monkeypatch.setattr(module, "complete_messages", fake_complete_messages)
    monkeypatch.setattr(
        module,
        "compact_user_turns",
        lambda turns: ([], {"premise": None, "policies": {}, "version": 2}, "Need clarification."),
    )

    module.main()
    output = capsys.readouterr().out
    report = consume_last_report()

    assert report is not None
    assert len(calls) == 2
    assert report["compiler_pass"] is True
    assert report["compiler_compact_pass"] is False
    assert "compiler+compact: FAIL" in output


def test_demo_04_reports_denylisted_tool_avoidance(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_demo_module("04_llm_tool_denylist_guardrail.py")
    monkeypatch.setattr(
        module,
        "complete_messages",
        _sequenced_outputs(
            [
                "TOOL:docker\nACTION:Use docker run.",
                "TOOL:kubectl\nACTION:Use kubectl apply.",
                "TOOL:kubectl\nACTION:Use kubectl rollout status.",
            ]
        ),
    )

    module.main()
    output = capsys.readouterr().out
    report = consume_last_report()

    assert report is not None
    assert report["name"].startswith("04_tool_governance")
    assert report["baseline_pass"] is False
    assert report["compiler_pass"] is True
    assert report["compiler_compact_pass"] is True
    assert report["demo_pass"] is True
    assert "baseline: FAIL" in output
    assert "compiler: PASS" in output
    assert "compiler+compact: PASS" in output


def test_demo_04_compact_clarify_branch_skips_compact_tool_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_demo_module("04_llm_tool_denylist_guardrail.py")
    calls: list[object] = []

    def fake_complete_messages(messages: object) -> str:
        calls.append(messages)
        if len(calls) == 1:
            return "TOOL:docker\nACTION:use docker"
        return "TOOL:kubectl\nACTION:use kubectl"

    monkeypatch.setattr(module, "complete_messages", fake_complete_messages)
    monkeypatch.setattr(
        module,
        "compact_user_turns",
        lambda turns: ([], {"premise": None, "policies": {}, "version": 2}, "Need clarification."),
    )

    module.main()
    output = capsys.readouterr().out
    report = consume_last_report()

    assert report is not None
    assert len(calls) == 2
    assert report["compiler_pass"] is True
    assert report["compiler_compact_pass"] is False
    assert "compiler+compact: FAIL" in output


def test_demo_04_baseline_and_compiler_share_same_tool_oracle(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_demo_module("04_llm_tool_denylist_guardrail.py")
    allowed_tool_response = "TOOL:kubectl\nACTION:use kubectl apply"
    monkeypatch.setattr(
        module,
        "complete_messages",
        _sequenced_outputs(
            [
                allowed_tool_response,
                allowed_tool_response,
                allowed_tool_response,
            ]
        ),
    )

    module.main()
    output = capsys.readouterr().out
    report = consume_last_report()

    assert report is not None
    assert report["baseline_pass"] is True
    assert report["compiler_pass"] is True
    assert report["compiler_compact_pass"] is True
    assert "baseline: PASS" in output
    assert "compiler: PASS" in output
