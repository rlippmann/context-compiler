from pathlib import Path

from _api_contract_harness import (
    assert_shape,
    assert_signature_matches,
    load_api_contract,
    resolve_probe_value,
    validate_engine_member_probes,
    validate_engine_member_runtime,
    validate_export_kind,
)

import context_compiler

_CONTRACT_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "api" / "public-api-v2.json"
)


def _load_contract() -> dict[str, object]:
    return load_api_contract(
        _CONTRACT_PATH,
        expected_module="context_compiler",
        allowed_export_kinds={"callable", "constant", "type_alias", "type", "class"},
        allowed_engine_member_kinds={"method", "property"},
    )


def test_api_contract_fixture_matches_python_public_surface() -> None:
    contract = _load_contract()

    assert contract["kind"] == "api-contract"
    exports = contract["exports"]
    expected_exports = exports["names"]
    export_members = exports["members"]

    assert context_compiler.__all__ == expected_exports
    for name in expected_exports:
        assert hasattr(context_compiler, name), name
        assert name in context_compiler.__all__, name

    for name, export_contract in export_members.items():
        exported = getattr(context_compiler, name)
        validate_export_kind(name, exported, export_contract["kind"])
        if "value" in export_contract:
            assert exported == export_contract["value"], name
        if "signature" in export_contract:
            assert_signature_matches(exported, export_contract["signature"], name)
        for probe in export_contract.get("shape_probes", []):
            args = [resolve_probe_value(value) for value in probe.get("args", [])]
            kwargs = {
                key: resolve_probe_value(value) for key, value in probe.get("kwargs", {}).items()
            }
            result = exported(*args, **kwargs)
            assert_shape(result, probe["return_shape"], contract)

    engine = context_compiler.Engine()
    engine_contract = contract["engine"]["public_members"]
    expected_members = engine_contract["members"]

    actual_public_members = sorted(name for name in dir(engine) if not name.startswith("_"))
    assert actual_public_members == sorted(expected_members.keys())

    engine_type = type(engine)
    for name, member_contract in expected_members.items():
        assert hasattr(engine, name), name
        validate_engine_member_runtime(engine_type, engine, name, member_contract)
        validate_engine_member_probes(engine, name, member_contract, contract)


def test_api_contract_fixture_forbidden_exports_are_not_present() -> None:
    contract = _load_contract()

    for name in contract.get("forbidden_exports", []):
        assert name not in context_compiler.__all__, name
        assert not hasattr(context_compiler, name), name


def test_public_annotation_dependencies_are_importable_from_root() -> None:
    assert context_compiler.PolicyValue is not None


def test_api_contract_fixture_has_unique_entries() -> None:
    contract = _load_contract()
    export_names = contract["exports"]["names"]
    assert len(export_names) == len(set(export_names))

    forbidden_exports = contract.get("forbidden_exports", [])
    assert len(forbidden_exports) == len(set(forbidden_exports))
    assert not (set(forbidden_exports) & set(export_names))

    export_member_names = list(contract["exports"]["members"].keys())
    assert len(export_member_names) == len(set(export_member_names))
    assert set(export_member_names) == set(export_names)

    for export_name, export_contract in contract["exports"]["members"].items():
        kind = export_contract["kind"]
        assert kind in {"callable", "constant", "type_alias", "type", "class"}, export_name
        if kind == "callable":
            assert "signature" in export_contract, export_name
        else:
            assert "signature" not in export_contract, export_name

    engine_members = list(contract["engine"]["public_members"]["members"].keys())
    assert len(engine_members) == len(set(engine_members))

    for member_name, member_contract in contract["engine"]["public_members"]["members"].items():
        kind = member_contract["kind"]
        assert kind in {"method", "property"}, member_name
        if kind == "property":
            assert "signature" not in member_contract, member_name
        else:
            assert "signature" in member_contract, member_name
