import inspect
import json
from pathlib import Path

import context_compiler

_CONTRACT_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "api" / "public-api-v1.json"
)


def _load_contract() -> dict[str, object]:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


def _assert_signature_matches(obj: object, expected: dict[str, object], label: str) -> None:
    signature = inspect.signature(obj)
    params = list(signature.parameters.values())
    expected_params = expected["params"]

    assert len(params) == len(expected_params), label
    for actual, expected_param in zip(params, expected_params, strict=True):
        assert actual.name == expected_param["name"], label
        assert actual.kind.name == expected_param["kind"], label
        assert (actual.default is not inspect.Signature.empty) is expected_param["has_default"], (
            label
        )


def test_api_contract_fixture_matches_python_public_surface() -> None:
    contract = _load_contract()

    assert contract["kind"] == "api-contract"
    exports = contract["exports"]
    expected_exports = exports["names"]

    assert context_compiler.__all__ == expected_exports
    for name in expected_exports:
        assert hasattr(context_compiler, name), name
        assert name in context_compiler.__all__, name

    for name, signature_contract in exports.get("signatures", {}).items():
        _assert_signature_matches(getattr(context_compiler, name), signature_contract, name)

    engine = context_compiler.create_engine()
    engine_contract = contract["engine"]["public_members"]
    expected_members = engine_contract["members"]

    actual_public_members = sorted(name for name in dir(engine) if not name.startswith("_"))
    assert actual_public_members == sorted(expected_members.keys())

    engine_type = type(engine)
    for name, member_contract in expected_members.items():
        assert hasattr(engine, name), name
        kind = member_contract["kind"]

        if kind == "property":
            assert isinstance(inspect.getattr_static(engine_type, name), property), name
            continue

        assert callable(getattr(engine, name)), name
        _assert_signature_matches(getattr(engine, name), member_contract["signature"], name)


def test_api_contract_fixture_has_unique_entries() -> None:
    contract = _load_contract()
    export_names = contract["exports"]["names"]
    assert len(export_names) == len(set(export_names))

    export_signature_names = list(contract["exports"].get("signatures", {}).keys())
    assert len(export_signature_names) == len(set(export_signature_names))
    assert set(export_signature_names).issubset(set(export_names))

    engine_members = list(contract["engine"]["public_members"]["members"].keys())
    assert len(engine_members) == len(set(engine_members))

    for member_name, member_contract in contract["engine"]["public_members"]["members"].items():
        kind = member_contract["kind"]
        assert kind in {"method", "property"}, member_name
        if kind == "property":
            assert "signature" not in member_contract, member_name
        else:
            assert "signature" in member_contract, member_name
