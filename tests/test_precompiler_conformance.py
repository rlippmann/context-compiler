import json
from pathlib import Path

from experimental.preprocessor.heuristic_precompiler import precompile_heuristic
from experimental.preprocessor.output_validation import validate_precompiler_output

_PRECOMPILER_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "precompiler"


def _fixture_paths() -> list[Path]:
    return sorted(_PRECOMPILER_FIXTURES_DIR.glob("*.json"))


def _load_fixture(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_result(message: str) -> dict[str, object]:
    result = precompile_heuristic(message)
    output = result["directive"] if result["outcome"] == "directive" else None
    normalized = {
        "classification": result["outcome"],
        "output": output,
    }

    # Enforce the validation boundary: only validated directive output may pass.
    validated = validate_precompiler_output(output)
    if normalized["classification"] == "directive":
        assert validated["classification"] == "directive"
        assert validated["output"] == output
    else:
        assert output is None
        assert validated["output"] is None

    return normalized


def test_precompiler_conformance_fixtures() -> None:
    for path in _fixture_paths():
        fixture = _load_fixture(path)
        expected = fixture["expected"]
        input_text = fixture["input"]
        fixture_name = fixture["name"]

        assert isinstance(expected, dict), fixture_name
        assert isinstance(input_text, str), fixture_name

        # Deterministic replay check.
        first = _normalize_result(input_text)
        second = _normalize_result(input_text)
        assert first == second, fixture_name
        assert first == expected, fixture_name
