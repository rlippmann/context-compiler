import json
from pathlib import Path

import context_compiler

_CONTRACT_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "api" / "public-api-v1.json"
)


def _load_contract() -> dict[str, object]:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


def test_api_contract_fixture_matches_python_public_surface() -> None:
    contract = _load_contract()

    assert contract["kind"] == "api-contract"
    for name in contract["required_exports"]:
        assert hasattr(context_compiler, name), name
        assert name in context_compiler.__all__, name

    engine = context_compiler.create_engine()
    for name in contract["engine"]["required_members"]:
        assert hasattr(engine, name), name


def test_api_contract_fixture_has_unique_entries() -> None:
    contract = _load_contract()
    required_exports = contract["required_exports"]
    assert len(required_exports) == len(set(required_exports))
    required_members = contract["engine"]["required_members"]
    assert len(required_members) == len(set(required_members))
