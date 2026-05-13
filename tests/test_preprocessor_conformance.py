import json
import re
from pathlib import Path

from experimental.preprocessor.heuristic_preprocessor import preprocess_heuristic
from experimental.preprocessor.output_validation import validate_preprocessor_output

_PREPROCESSOR_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "preprocessor"


def _behavior_fixture_paths() -> list[Path]:
    return sorted(path for path in _PREPROCESSOR_FIXTURES_DIR.glob("*.json"))


def _load_fixture(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_result(message: str) -> dict[str, object]:
    result = preprocess_heuristic(message)
    output = result["directive"] if result["outcome"] == "directive" else None
    normalized = {
        "classification": result["outcome"],
        "output": output,
    }

    # Enforce the validation boundary: only validated directive output may pass.
    validated = validate_preprocessor_output(output)
    if normalized["classification"] == "directive":
        assert validated["classification"] == "directive"
        assert validated["output"] == output
    else:
        assert output is None
        assert validated["output"] is None

    return normalized


def _normalize_validator_result(
    raw_output: object, source_input: str | None = None
) -> dict[str, object]:
    validated = validate_preprocessor_output(raw_output, source_input=source_input)
    return {
        "classification": validated["classification"],
        "output": validated["output"],
    }


def _derived_risky_rewrite_candidates(source_input: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", source_input.strip().lower())
    candidates: list[str] = []

    set_premise_to_match = re.fullmatch(r"set premise to\s+(.+\S)", normalized)
    if set_premise_to_match is not None:
        payload = set_premise_to_match.group(1).strip()
        candidates.append(f"set premise {payload}")

    change_premise_missing_to_match = re.fullmatch(r"change premise\s+(?!to\b)(.+\S)", normalized)
    if change_premise_missing_to_match is not None:
        payload = change_premise_missing_to_match.group(1).strip()
        candidates.append(f"change premise to {payload}")

    return candidates


def test_preprocessor_conformance_fixtures() -> None:
    for path in _behavior_fixture_paths():
        fixture = _load_fixture(path)
        if path.name.startswith("public-api-"):
            continue

        expected = fixture.get("expected")
        fixture_name = fixture.get("name", path.name)
        kind = fixture.get("kind", "heuristic")

        assert isinstance(expected, dict), fixture_name

        if kind == "heuristic":
            input_text = fixture.get("input")
            assert isinstance(input_text, str), fixture_name

            # Deterministic replay check.
            first = _normalize_result(input_text)
            second = _normalize_result(input_text)
            assert first == second, fixture_name
            assert first == expected, fixture_name
            continue

        assert kind == "validator", fixture_name
        assert "raw_output" in fixture, fixture_name
        raw_output = fixture["raw_output"]
        source_input_obj = fixture.get("source_input")
        source_input = source_input_obj if isinstance(source_input_obj, str) else None

        # Deterministic replay check.
        first = _normalize_validator_result(raw_output, source_input=source_input)
        second = _normalize_validator_result(raw_output, source_input=source_input)
        assert first == second, fixture_name
        assert first == expected, fixture_name


def test_engine_owned_near_misses_are_reject_only_for_fallback_rewrites() -> None:
    # Engine-owned near-misses must not be canonicalized by the preprocessor and
    # must remain unknown even if fallback proposes a plausible canonical rewrite.
    for path in _behavior_fixture_paths():
        fixture = _load_fixture(path)
        if path.name.startswith("public-api-"):
            continue
        if fixture.get("kind", "heuristic") != "heuristic":
            continue
        expected = fixture["expected"]
        input_text = fixture["input"]
        fixture_name = fixture["name"]

        assert isinstance(expected, dict), fixture_name
        assert isinstance(input_text, str), fixture_name

        if expected.get("classification") != "unknown" or expected.get("output") is not None:
            continue

        for candidate in _derived_risky_rewrite_candidates(input_text):
            validated = validate_preprocessor_output(candidate, source_input=input_text)
            assert validated["classification"] != "directive", fixture_name
