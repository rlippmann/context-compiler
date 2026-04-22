import runpy
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"
pytestmark = pytest.mark.contract


@pytest.mark.parametrize(
    ("script_name", "expected_markers"),
    [
        (
            "01_persistent_guardrails.py",
            (
                "Host prompt construction with persisted policy:",
                "- prohibited policy items: peanuts",
            ),
        ),
        (
            "02_configuration_and_correction.py",
            (
                "state after explicit premise change:",
                "- premise: vegan curry",
            ),
        ),
        (
            "03_ambiguity_with_clarification.py",
            (
                "Host behavior: clarification pending, do NOT call LLM.",
                "Remove or replace it before using it.",
            ),
        ),
        (
            "04_tool_governance_denylist.py",
            (
                "Host-side tool denylist behavior:",
                "Blocked tool: docker",
            ),
        ),
        (
            "05_llm_integration_pattern.py",
            (
                "Host action: passthrough -> call fake_llm() without state",
                "Host action: update -> call fake_llm() with compiled state",
            ),
        ),
        (
            "06_transcript_replay.py",
            (
                "Replay from fresh engine (compile_transcript):",
                "Replay onto current engine (engine.apply_transcript):",
            ),
        ),
        (
            "07_single_policy_correction.py",
            (
                "final state:",
                "- use policies: peanuts",
            ),
        ),
    ],
)
def test_examples_scripts_smoke(
    script_name: str,
    expected_markers: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script_path = EXAMPLES_DIR / script_name
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    monkeypatch.syspath_prepend(str(EXAMPLES_DIR))
    monkeypatch.setattr("sys.argv", [str(script_path)])

    runpy.run_path(str(script_path), run_name="__main__")

    output = capsys.readouterr().out
    for marker in expected_markers:
        assert marker in output
