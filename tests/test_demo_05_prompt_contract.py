import importlib.util
import runpy
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_demo_05_applies_same_output_format_contract_to_all_three_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_messages: list[list[dict[str, str]]] = []

    def fake_complete_messages(messages: list[dict[str, str]]) -> str:
        captured_messages.append(messages)
        return "PREMISE:vegetarian curry\n- vegetables\n- coconut milk\n- simmer"

    import demos.llm_client as llm_client

    monkeypatch.setattr(llm_client, "complete_messages", fake_complete_messages)

    demo_path = REPO_ROOT / "demos" / "05_llm_prompt_drift_vs_state.py"
    monkeypatch.setattr("sys.argv", [str(demo_path)])
    runpy.run_path(str(demo_path), run_name="__main__")

    assert len(captured_messages) == 3
    for messages in captured_messages:
        assert messages
        assert messages[0]["role"] == "system"
        assert "First line must be exactly PREMISE:<value>." in messages[0]["content"]


def test_demo_05_compact_path_injects_premise_anchor_when_directive_is_compacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_messages: list[list[dict[str, str]]] = []

    def fake_complete_messages(messages: list[dict[str, str]]) -> str:
        captured_messages.append(messages)
        return "PREMISE:vegetarian curry\n- vegetables\n- coconut milk\n- simmer"

    import demos.llm_client as llm_client

    monkeypatch.setattr(llm_client, "complete_messages", fake_complete_messages)

    demo_path = REPO_ROOT / "demos" / "05_llm_prompt_drift_vs_state.py"
    monkeypatch.setattr("sys.argv", [str(demo_path)])
    runpy.run_path(str(demo_path), run_name="__main__")

    assert len(captured_messages) == 3
    compact_messages = captured_messages[2]
    assert any(
        message["role"] == "user" and message["content"] == "Premise reminder: vegetarian curry"
        for message in compact_messages
    )


def test_demo_05_premise_match_ignores_trailing_sentence_punctuation() -> None:
    demo_path = REPO_ROOT / "demos" / "05_llm_prompt_drift_vs_state.py"
    spec = importlib.util.spec_from_file_location("demo_05_for_premise_match", demo_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.premise_matches_expected("PREMISE: vegetarian curry.\nDinner Plan:\n- tofu")
    assert module.premise_matches_expected("PREMISE: vegetarian curry!\nDinner Plan:\n- tofu")
    assert not module.premise_matches_expected("PREMISE: vegan curry.\nDinner Plan:\n- tofu")
