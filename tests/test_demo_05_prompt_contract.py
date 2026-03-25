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
