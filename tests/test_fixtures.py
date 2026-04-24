import json
from pathlib import Path

from context_compiler import compile_transcript, create_engine

_STEP_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "conformance" / "step"
_TRANSCRIPT_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "transcript"
)


def _json_files(dir_path: Path) -> list[Path]:
    return sorted(dir_path.glob("*.json"))


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_step_fixtures() -> None:
    for path in _json_files(_STEP_FIXTURES_DIR):
        fixture = _load(path)
        fixture_id = fixture["id"]

        assert fixture["kind"] == "step", fixture_id

        engine = create_engine(state=fixture["initial_state"])
        prelude = fixture.get("prelude", [])
        for prior_input in prelude:
            engine.step(prior_input)
        decision = engine.step(fixture["input"])

        expected = fixture["expected"]
        expected_decision = expected["decision"]

        assert decision["kind"] == expected_decision["kind"], fixture_id

        if decision["kind"] == "clarify":
            assert decision["state"] == expected_decision["state"], fixture_id
            expected_prompt = expected_decision["prompt_to_user"]
            actual_prompt = decision["prompt_to_user"]
            if expected_prompt is None:
                assert isinstance(actual_prompt, str) and actual_prompt != "", fixture_id
            else:
                assert actual_prompt == expected_prompt, fixture_id
        else:
            assert decision == expected_decision, fixture_id

        if decision["kind"] == "update":
            assert decision["state"] == engine.state, fixture_id

        assert engine.state == expected["state"], fixture_id


def test_transcript_fixtures() -> None:
    for path in _json_files(_TRANSCRIPT_FIXTURES_DIR):
        fixture = _load(path)
        fixture_id = fixture["id"]

        assert fixture["kind"] == "transcript", fixture_id

        result = compile_transcript(fixture["messages"])

        if (
            isinstance(result, dict)
            and set(result.keys()) == {"kind", "prompt_to_user"}
            and isinstance(result.get("prompt_to_user"), str)
        ):
            normalized = {
                "clarify": {
                    "prompt_to_user": result["prompt_to_user"],
                }
            }
        else:
            normalized = {"state": result}

        assert normalized == fixture["expected"], fixture_id
