import difflib
import json
from pathlib import Path

import pytest
from _decision_test_helpers import decision_observation

from context_compiler import Engine

_STRUCTURED_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "engine-regression" / "structured"
)
_SCENARIOS_DIR = _STRUCTURED_FIXTURES_DIR / "scenarios"
_EXPECTED_DIR = _STRUCTURED_FIXTURES_DIR / "expected"


def _json_files(dir_path: Path) -> list[Path]:
    return sorted(dir_path.glob("*.json"))


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_fixture_path_matches_id(path: Path, fixture_id: object, label: str) -> None:
    assert path.stem == fixture_id, f"{fixture_id}: filename/id mismatch for {label}"


def _assert_allowed_keys(
    obj: dict[str, object], allowed_keys: set[str], fixture_id: object, label: str
) -> None:
    assert set(obj) == allowed_keys, f"{fixture_id}: invalid keys for {label}"


def _validate_structured_scenario_fixture(scenario: dict[str, object], fixture_id: object) -> None:
    _assert_allowed_keys(
        scenario,
        {"id", "inputs"} | ({"description"} & set(scenario)) | ({"initial_state"} & set(scenario)),
        fixture_id,
        "scenario",
    )
    if "description" in scenario:
        assert isinstance(scenario["description"], str), fixture_id
    if "initial_state" in scenario:
        assert scenario["initial_state"] is None or isinstance(scenario["initial_state"], dict), (
            fixture_id
        )
    inputs = scenario["inputs"]
    assert isinstance(inputs, list), fixture_id
    assert all(isinstance(item, str) for item in inputs), fixture_id


def _validate_structured_expected_fixture(expected: dict[str, object], fixture_id: object) -> None:
    _assert_allowed_keys(expected, {"id", "turns"}, fixture_id, "expected")
    turns = expected["turns"]
    assert isinstance(turns, list), fixture_id
    for turn in turns:
        assert isinstance(turn, dict), fixture_id
        _assert_allowed_keys(turn, {"input", "decision", "state"}, fixture_id, "expected.turn")
        assert isinstance(turn["input"], str), fixture_id
        assert isinstance(turn["state"], dict), fixture_id

        decision = turn["decision"]
        assert isinstance(decision, dict), fixture_id
        if decision.get("kind") == "error":
            _assert_allowed_keys(
                decision,
                {"kind", "failure", "directive", "repairs", "message"},
                fixture_id,
                "expected.turn.decision",
            )
        elif decision.get("kind") == "update":
            _assert_allowed_keys(
                decision, {"kind", "changed"}, fixture_id, "expected.turn.decision"
            )
        else:
            _assert_allowed_keys(
                decision, {"kind", "message"}, fixture_id, "expected.turn.decision"
            )
        assert isinstance(decision["kind"], str), fixture_id
        if decision["kind"] == "error":
            assert isinstance(decision["message"], str), fixture_id
        elif decision["kind"] == "update":
            assert isinstance(decision["changed"], bool), fixture_id
        else:
            assert decision["message"] is None, fixture_id


def _state_diff(expected: object, actual: object) -> str:
    expected_lines = json.dumps(expected, indent=2, sort_keys=True).splitlines()
    actual_lines = json.dumps(actual, indent=2, sort_keys=True).splitlines()
    return "\n".join(
        difflib.unified_diff(
            expected_lines,
            actual_lines,
            fromfile="expected_state",
            tofile="actual_state",
            lineterm="",
        )
    )


def _state_observation(engine: object) -> dict[str, object]:
    return {
        "premise": engine.premise,
        "policies": dict(engine.policies),
        "version": 2,
    }


@pytest.mark.contract
def test_structured_regression_scenarios() -> None:
    for scenario_path in _json_files(_SCENARIOS_DIR):
        scenario = _load_json(scenario_path)
        scenario_id = scenario["id"]
        expected_path = _EXPECTED_DIR / f"{scenario_id}.json"
        expected = _load_json(expected_path)

        _assert_fixture_path_matches_id(scenario_path, scenario_id, "scenario")
        _assert_fixture_path_matches_id(expected_path, expected["id"], "expected")
        _validate_structured_scenario_fixture(scenario, scenario_id)
        _validate_structured_expected_fixture(expected, scenario_id)
        assert expected["id"] == scenario_id, f"scenario_id_mismatch: {scenario_id}"

        engine = Engine()

        initial_state = scenario.get("initial_state")
        if initial_state is not None:
            engine.import_json(json.dumps(initial_state, sort_keys=True, separators=(",", ":")))

        inputs = scenario["inputs"]
        expected_turns = expected["turns"]
        assert len(inputs) == len(expected_turns), f"turn_count_mismatch: {scenario_id}"

        for turn_index, user_input in enumerate(inputs):
            decision = decision_observation(engine.step(user_input))
            state = _state_observation(engine)
            expected_turn = expected_turns[turn_index]

            context = f"scenario={scenario_id} turn={turn_index} input={user_input!r}"

            assert expected_turn["input"] == user_input, f"{context} input_mismatch"

            expected_decision = expected_turn["decision"]
            if expected_decision["kind"] == "error":
                assert decision["kind"] == expected_decision["kind"], f"{context} decision_mismatch"
                for field, value in expected_decision.items():
                    assert decision[field] == value, f"{context} decision_mismatch"
            else:
                assert decision == expected_decision, f"{context} decision_mismatch"

            expected_state = expected_turn["state"]
            if state != expected_state:
                diff = _state_diff(expected_state, state)
                pytest.fail(f"{context} state_mismatch\n{diff}")


def test_structured_expected_validator_rejects_unknown_turn_decision_field() -> None:
    expected = {
        "id": "invalid_structured_expected",
        "turns": [
            {
                "input": "use docker",
                "decision": {
                    "kind": "update",
                    "unexpected": True,
                },
                "state": {"premise": None, "policies": {"docker": "use"}, "version": 2},
            }
        ],
    }

    with pytest.raises(AssertionError, match="invalid keys for expected.turn.decision"):
        _validate_structured_expected_fixture(expected, expected["id"])


def test_structured_scenario_validator_allows_missing_optional_metadata() -> None:
    scenario = {
        "id": "scenario_without_optional_metadata",
        "inputs": ["use docker"],
    }

    _validate_structured_scenario_fixture(scenario, scenario["id"])


def test_structured_scenario_identity_rejects_filename_id_mismatch() -> None:
    path = Path("/tmp/scenario_file.json")

    with pytest.raises(AssertionError, match="filename/id mismatch for scenario"):
        _assert_fixture_path_matches_id(path, "different_scenario_id", "scenario")


def test_structured_expected_identity_rejects_filename_id_mismatch() -> None:
    path = Path("/tmp/expected_file.json")

    with pytest.raises(AssertionError, match="filename/id mismatch for expected"):
        _assert_fixture_path_matches_id(path, "different_expected_id", "expected")
