import runpy
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_demo_07_prints_separate_assertion_outcome_when_paths_pass(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Force all paths to emit expected premise tag, which yields:
    # baseline PASS, compiler PASS, compiler+compact PASS, but demo assertion not demonstrated
    # because weak path also passes.
    def fake_complete_messages(messages: list[dict[str, str]]) -> str:
        del messages
        return "PREMISE:vegan curry\n- list item"

    import demos.llm_client as llm_client

    monkeypatch.setattr(llm_client, "complete_messages", fake_complete_messages)

    demo_path = REPO_ROOT / "demos" / "07_llm_prompt_vs_state.py"
    monkeypatch.setattr("sys.argv", [str(demo_path)])
    runpy.run_path(str(demo_path), run_name="__main__")

    output = capsys.readouterr().out
    assert "baseline: PASS" in output
    assert "compiler: PASS" in output
    assert "compiler+compact: PASS" in output
    assert "assertion: not demonstrated" in output
    assert (
        "result: compiled-state paths were not clearly more reliable than prompt-only in this run"
        in output
    )
