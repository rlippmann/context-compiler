import difflib
import json
from pathlib import Path

import pytest

from context_compiler import create_engine

_STRUCTURED_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "engine-regression" / "structured"
)
_SCENARIOS_DIR = _STRUCTURED_FIXTURES_DIR / "scenarios"
_EXPECTED_DIR = _STRUCTURED_FIXTURES_DIR / "expected"


def _json_files(dir_path: Path) -> list[Path]:
    return sorted(dir_path.glob("*.json"))


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _checkpoint_diff(expected: object, actual: object) -> str:
    expected_lines = json.dumps(expected, indent=2, sort_keys=True).splitlines()
    actual_lines = json.dumps(actual, indent=2, sort_keys=True).splitlines()
    return "\n".join(
        difflib.unified_diff(
            expected_lines,
            actual_lines,
            fromfile="expected_checkpoint",
            tofile="actual_checkpoint",
            lineterm="",
        )
    )


@pytest.mark.contract
def test_structured_regression_scenarios() -> None:
    for scenario_path in _json_files(_SCENARIOS_DIR):
        scenario = _load_json(scenario_path)
        scenario_id = scenario["id"]
        expected_path = _EXPECTED_DIR / f"{scenario_id}.json"
        expected = _load_json(expected_path)

        assert expected["id"] == scenario_id, f"scenario_id_mismatch: {scenario_id}"

        engine = create_engine()

        initial_checkpoint = scenario.get("initial_checkpoint")
        if initial_checkpoint is not None:
            engine.import_checkpoint(initial_checkpoint)

        inputs = scenario["inputs"]
        expected_turns = expected["turns"]
        assert len(inputs) == len(expected_turns), f"turn_count_mismatch: {scenario_id}"

        for turn_index, user_input in enumerate(inputs):
            decision = engine.step(user_input)
            checkpoint = engine.export_checkpoint()
            expected_turn = expected_turns[turn_index]

            context = f"scenario={scenario_id} turn={turn_index} input={user_input!r}"

            assert expected_turn["input"] == user_input, f"{context} input_mismatch"

            expected_decision = expected_turn["decision"]
            assert decision["kind"] == expected_decision["kind"], (
                f"{context} decision_kind_mismatch"
            )
            assert decision["prompt_to_user"] == expected_decision["prompt_to_user"], (
                f"{context} prompt_to_user_mismatch"
            )

            expected_checkpoint = expected_turn["checkpoint"]
            if checkpoint != expected_checkpoint:
                diff = _checkpoint_diff(expected_checkpoint, checkpoint)
                pytest.fail(f"{context} checkpoint_mismatch\n{diff}")
