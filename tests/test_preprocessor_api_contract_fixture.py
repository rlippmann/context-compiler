import json
from pathlib import Path

import experimental.preprocessor as preprocessor

_CONTRACT_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "preprocessor" / "public-api-v1.json"
)


def _load_contract() -> dict[str, object]:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


def test_preprocessor_api_contract_fixture_matches_public_surface() -> None:
    contract = _load_contract()

    assert contract["kind"] == "api-contract"

    for name in contract["required_exports"]:
        assert hasattr(preprocessor, name), name
        assert name in preprocessor.__all__, name


def test_preprocessor_api_contract_fixture_has_unique_entries() -> None:
    contract = _load_contract()

    required_exports = contract["required_exports"]
    assert len(required_exports) == len(set(required_exports))
