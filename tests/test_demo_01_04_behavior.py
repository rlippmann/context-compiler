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
