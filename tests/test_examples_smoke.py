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
                "- premise: project deadline is Thursday",
            ),
        ),
        (
            "03_ambiguity_with_error.py",
            (
                "Host behavior: error returned, do NOT call LLM.",
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
                "Host action: no_directive -> core recognized no canonical directive",
                "Host action: update -> call fake_llm() with compiled state",
            ),
        ),
        (
            "06_step_sequence_and_state_restore.py",
            (
                "Sequence directives through engine.step():",
                "JSON restore keeps authority state:",
            ),
        ),
        (
            "07_single_policy_correction.py",
            (
                "final state:",
                "- use policies: peanuts",
            ),
        ),
        (
            "08_apply_directive_decisions.py",
            (
                "engine.step() raw input boundary:",
                "NoDirectiveDecision.kind: no_directive",
                "step raw input: prohibit docker",
                "terminal semantic error follow-up:",
                "State unchanged after missing-source replacement: True",
                "No repair applied automatically; later input is evaluated independently.",
                "Later unrelated input: NoDirectiveDecision",
                "decompose_directive() + engine.apply_directive() canonical boundary:",
                "CanonicalDirective: prohibit docker",
                "UpdateDecision.changed: True",
                "SemanticErrorDecision.failure: item_prohibited",
                "SemanticErrorDecision.directive: use docker",
                "SemanticErrorDecision.repairs: remove policy docker, use docker",
                'SemanticErrorDecision.message: "docker" is currently prohibited.',
                "Applying selected repairs:",
            ),
        ),
    ],
)
def test_examples_scripts_smoke(
    script_name: str,
    expected_markers: tuple[str, ...],
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
