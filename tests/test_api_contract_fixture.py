import inspect
import json
from pathlib import Path

import context_compiler

_CONTRACT_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "api" / "public-api-v1.json"
)


def _load_contract() -> dict[str, object]:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


def _json_type_matches(value: object, expected: str) -> bool:
    return {
        "null": value is None,
        "string": isinstance(value, str),
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "boolean": isinstance(value, bool),
        "number": isinstance(value, int | float) and not isinstance(value, bool),
    }[expected]


def _resolve_probe_value(value: object) -> object:
    if not isinstance(value, dict) or "fixture" not in value:
        return value

    fixture = value["fixture"]
    if fixture == "empty_engine":
        return context_compiler.create_engine()

    raise AssertionError(f"Unknown probe fixture: {fixture}")


def _assert_shape(value: object, shape: dict[str, object], contract: dict[str, object]) -> None:
    if "kind" in shape and shape["kind"] == "engine_instance":
        assert isinstance(value, context_compiler.Engine)
        expected_members = contract["engine"]["public_members"]["members"]
        actual_members = sorted(name for name in dir(value) if not name.startswith("_"))
        assert actual_members == sorted(expected_members.keys())
        return

    expected_types = shape["type"]
    if isinstance(expected_types, str):
        expected_types = [expected_types]
    assert any(_json_type_matches(value, expected_type) for expected_type in expected_types)

    if "const" in shape:
        assert value == shape["const"]

    if isinstance(value, dict):
        required_keys = shape.get("required_keys", [])
        assert set(required_keys).issubset(value)
        properties = shape.get("properties", {})
        for key, property_shape in properties.items():
            if key in value:
                _assert_shape(value[key], property_shape, contract)


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


def _assert_export_kind(name: str, exported: object, expected_kind: str) -> None:
    if expected_kind == "callable":
        assert inspect.isroutine(exported), name
        return
    if expected_kind == "constant":
        assert not inspect.isroutine(exported) and not inspect.isclass(exported), name
        return
    if expected_kind == "type_alias":
        assert not inspect.isroutine(exported) and not inspect.isclass(exported), name
        return
    if expected_kind == "type":
        assert inspect.isclass(exported), name
        return
    assert expected_kind == "class", name
    assert inspect.isclass(exported), name


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
        _assert_export_kind(name, exported, export_contract["kind"])
        if "value" in export_contract:
            assert exported == export_contract["value"], name
        if "signature" in export_contract:
            _assert_signature_matches(exported, export_contract["signature"], name)
        for probe in export_contract.get("shape_probes", []):
            kwargs = {
                key: _resolve_probe_value(value) for key, value in probe.get("kwargs", {}).items()
            }
            result = exported(**kwargs)
            _assert_shape(result, probe["return_shape"], contract)

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


def test_api_contract_fixture_forbidden_exports_are_not_present() -> None:
    contract = _load_contract()

    for name in contract.get("forbidden_exports", []):
        assert name not in context_compiler.__all__, name
        assert not hasattr(context_compiler, name), name


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
