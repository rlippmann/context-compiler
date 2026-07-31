import inspect
import json
from pathlib import Path

import context_compiler
import context_compiler.audit as audit

_CONTRACT_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "api" / "public-audit-v1.json"
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


def _assert_shape(value: object, shape: dict[str, object]) -> None:
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
                _assert_shape(value[key], property_shape)


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


def test_public_audit_contract_matches_surface() -> None:
    contract = _load_contract()

    exports = contract["exports"]
    expected_names = exports["names"]
    members = exports["members"]

    actual_names = sorted(name for name in audit.__all__)
    assert actual_names == sorted(expected_names)

    for name in expected_names:
        assert hasattr(audit, name), name

    for name, member in members.items():
        exported = getattr(audit, name)
        kind = member["kind"]
        if kind == "callable":
            assert inspect.isroutine(exported), name
            _assert_signature_matches(exported, member["signature"], name)
            for probe in member.get("shape_probes", []):
                args = [_resolve_probe_value(value) for value in probe.get("args", [])]
                kwargs = {
                    key: _resolve_probe_value(value)
                    for key, value in probe.get("kwargs", {}).items()
                }
                result = exported(*args, **kwargs)
                _assert_shape(result, probe["return_shape"])
            continue
        assert kind == "type", name
        assert inspect.isclass(exported), name
