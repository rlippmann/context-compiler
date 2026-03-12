import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from demos.common import consume_last_report  # noqa: E402


def _load_demo_module(filename: str) -> ModuleType:
    module_name = f"test_{filename[:-3]}"
    module_path = REPO_ROOT / "demos" / filename
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_demo_with_mocked_llm(
    module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    outputs: list[str],
) -> tuple[dict[str, Any], list[list[dict[str, str]]]]:
    calls: list[list[dict[str, str]]] = []
    output_iter: Iterator[str] = iter(outputs)

    def fake_complete_messages(messages: list[dict[str, str]]) -> str:
        calls.append(messages)
        try:
            return next(output_iter)
        except StopIteration as exc:
            raise AssertionError("Unexpected extra LLM call.") from exc

    monkeypatch.setattr(module, "complete_messages", fake_complete_messages)
    consume_last_report()
    module.main()
    try:
        next(output_iter)
    except StopIteration:
        pass
    else:
        raise AssertionError("Expected additional LLM call(s) were not made.")
    report = consume_last_report()
    assert report is not None
    return report, calls


def test_demo_01_constraint_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_demo_module("01_llm_constraint_drift.py")
    report, calls = _run_demo_with_mocked_llm(
        module,
        monkeypatch,
        outputs=[
            "Ingredients:\n- peanuts\n- coconut milk\nSteps:\n1. Cook.",
            (
                "I cannot comply with a peanut recipe because it is prohibited.\n"
                "Ingredients:\n- chickpeas\n- coconut milk\nSteps:\n1. Cook."
            ),
        ],
    )

    assert report["baseline_pass"] is False
    assert report["compiler_pass"] is True
    assert len(calls) == 2
    assert "policies.prohibit: peanuts" in calls[1][0]["content"]


def test_demo_02_correction_replacement(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_demo_module("02_llm_correction_replacement.py")
    report, calls = _run_demo_with_mocked_llm(
        module,
        monkeypatch,
        outputs=[
            (
                "FOCUS_PRIMARY: vegan curry\n"
                "Shopping list:\n- vegan curry paste\n- tofu\n"
                "Steps:\n1. Make vegan curry."
            ),
            (
                "FOCUS_PRIMARY: vegan curry\n"
                "Shopping list:\n- vegan curry paste\n- tofu\n"
                "Steps:\n1. Make vegan curry."
            ),
        ],
    )

    assert report["baseline_pass"] is True
    assert report["compiler_pass"] is True
    assert len(calls) == 2
    assert "facts.focus.primary: vegan curry" in calls[1][0]["content"]


def test_demo_03_ambiguity_block(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_demo_module("03_llm_ambiguity_block.py")
    report, calls = _run_demo_with_mocked_llm(
        module,
        monkeypatch,
        outputs=["ACTION:proceed"],
    )

    # Baseline path calls the LLM once; compiler-mediated clarify path should not call it.
    assert len(calls) == 1
    assert report["baseline_pass"] is False
    assert report["compiler_pass"] is True


def test_demo_03_non_clarify_path_calls_llm_for_mediated(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_demo_module("03_llm_ambiguity_block.py")

    class _EngineStub:
        def __init__(self) -> None:
            self.state: dict[str, object] = {
                "facts": {"focus.primary": None},
                "policies": {"prohibit": []},
                "version": 1,
            }

        def step(self, _text: str) -> dict[str, object]:
            return {"kind": "passthrough", "prompt_to_user": None, "state": None}

    monkeypatch.setattr(module, "create_engine", lambda: _EngineStub())
    report, calls = _run_demo_with_mocked_llm(
        module,
        monkeypatch,
        outputs=["ACTION:clarify", "ACTION:proceed"],
    )

    assert len(calls) == 2
    assert report["baseline_pass"] is True
    assert report["compiler_pass"] is False


def test_demo_04_tool_governance(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_demo_module("04_llm_tool_governance.py")
    report, calls = _run_demo_with_mocked_llm(
        module,
        monkeypatch,
        outputs=[
            "TOOL:docker\nACTION:Use docker deploy.",
            "TOOL:kubectl\nACTION:Use kubectl apply.",
        ],
    )

    assert report["baseline_pass"] is False
    assert report["compiler_pass"] is True
    assert len(calls) == 2
    assert "Candidate tools: docker, kubectl." in calls[1][0]["content"]
    assert "Prohibited: docker" in calls[1][0]["content"]


def test_demo_05_prompt_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_demo_module("05_llm_prompt_drift.py")
    report, calls = _run_demo_with_mocked_llm(
        module,
        monkeypatch,
        outputs=[
            ("DINNER_STYLE:vegetarian\nDinner plan:\n- chickpea curry\n- rice\nSteps:\n1. Cook."),
            ("DINNER_STYLE:vegetarian\nDinner plan:\n- chickpea curry\n- rice\nSteps:\n1. Cook."),
        ],
    )

    assert report["baseline_pass"] is True
    assert report["compiler_pass"] is True
    assert len(calls) == 2
    assert "facts.focus.primary: vegetarian curry" in calls[1][0]["content"]


def test_demo_01_negation_and_refusal_lines_do_not_count_as_violations() -> None:
    module = _load_demo_module("01_llm_constraint_drift.py")
    negated_recipe = "Ingredients:\n- no peanuts\n- coconut milk"
    refusal_with_prohibited_token = "I cannot comply with peanuts because that is prohibited."

    assert module.recipe_includes_prohibited_item(negated_recipe) is False
    assert module.recipe_includes_prohibited_item(refusal_with_prohibited_token) is False
