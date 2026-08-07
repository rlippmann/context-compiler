import inspect
import json
from pathlib import Path
from typing import Any

import context_compiler
import context_compiler.grammar as grammar

_JSON_TYPES = {"null", "string", "object", "array", "boolean", "number"}
_SIGNATURE_PARAM_KINDS = {kind.name for kind in inspect._ParameterKind}


def load_api_contract(
    path: Path,
    *,
    expected_module: str,
    allowed_export_kinds: set[str],
    allowed_engine_member_kinds: set[str] | None = None,
) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    _validate_contract(
        contract,
        expected_module=expected_module,
        allowed_export_kinds=allowed_export_kinds,
        allowed_engine_member_kinds=allowed_engine_member_kinds,
    )
    return contract


def json_type_matches(value: object, expected: str) -> bool:
    return {
        "null": value is None,
        "string": isinstance(value, str),
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "boolean": isinstance(value, bool),
        "number": isinstance(value, int | float) and not isinstance(value, bool),
    }[expected]


def resolve_probe_value(value: object) -> object:
    if not isinstance(value, dict) or "fixture" not in value:
        return value

    _assert_closed_keys(value, {"fixture"}, "probe fixture")
    fixture = value["fixture"]
    if fixture == "empty_engine":
        return context_compiler.create_engine()

    raise AssertionError(f"Unknown probe fixture: {fixture!r}")


def assert_shape(
    value: object, shape: dict[str, Any], contract: dict[str, Any] | None = None
) -> None:
    _validate_shape_spec(shape, "shape")

    if "kind" in shape and shape["kind"] == "engine_instance":
        assert isinstance(value, context_compiler.Engine)
        if contract is None:
            raise AssertionError("engine_instance shape requires the full contract")
        expected_members = contract["engine"]["public_members"]["members"]
        actual_members = sorted(name for name in dir(value) if not name.startswith("_"))
        assert actual_members == sorted(expected_members.keys())
        return

    if "kind" in shape and shape["kind"] == "canonical_directive":
        assert value == grammar.decompose_directive(shape["text"])
        return

    expected_types = shape["type"]
    if isinstance(expected_types, str):
        expected_types = [expected_types]
    assert any(json_type_matches(value, expected_type) for expected_type in expected_types)

    if "const" in shape:
        assert value == shape["const"]

    if isinstance(value, dict):
        required_keys = shape.get("required_keys", [])
        assert set(required_keys).issubset(value)
        properties = shape.get("properties", {})
        for key, property_shape in properties.items():
            if key in value:
                assert_shape(value[key], property_shape, contract)


def assert_signature_matches(obj: object, expected: dict[str, Any], label: str) -> None:
    _validate_signature_spec(expected, f"{label} signature")

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


def validate_export_kind(name: str, exported: object, expected_kind: str) -> None:
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
    if expected_kind == "class":
        assert inspect.isclass(exported), name
        return
    raise AssertionError(f"Unsupported export kind {expected_kind!r} for {name}")


def validate_engine_member_runtime(
    engine_type: type[object],
    engine: object,
    name: str,
    member_contract: dict[str, Any],
) -> None:
    kind = member_contract["kind"]
    if kind == "property":
        assert isinstance(inspect.getattr_static(engine_type, name), property), name
        return
    if kind == "method":
        assert callable(getattr(engine, name)), name
        assert_signature_matches(getattr(engine, name), member_contract["signature"], name)
        return
    raise AssertionError(f"Unsupported engine member kind {kind!r} for {name}")


def _validate_contract(
    contract: object,
    *,
    expected_module: str,
    allowed_export_kinds: set[str],
    allowed_engine_member_kinds: set[str] | None,
) -> None:
    _assert_type(contract, dict, "contract")

    allowed_top_level = {"id", "kind", "module", "exports"}
    if allowed_engine_member_kinds is not None:
        allowed_top_level |= {"target", "forbidden_exports", "engine"}
    _assert_closed_keys(contract, allowed_top_level, "contract")

    _require_fields(contract, {"id", "kind", "module", "exports"}, "contract")
    _assert_type(contract["id"], str, "contract.id")
    _assert_equal(contract["kind"], "api-contract", "contract.kind")
    _assert_equal(contract["module"], expected_module, "contract.module")

    forbidden_exports = contract.get("forbidden_exports", [])
    _assert_type(forbidden_exports, list, "contract.forbidden_exports")
    _assert_unique_strings(forbidden_exports, "contract.forbidden_exports")

    exports = contract["exports"]
    _validate_exports_spec(
        exports,
        allowed_export_kinds=allowed_export_kinds,
        label="contract.exports",
    )

    if allowed_engine_member_kinds is None:
        if "target" in contract:
            _assert_type(contract["target"], str, "contract.target")
        return

    _require_fields(contract, {"engine"}, "contract")
    if "target" in contract:
        _assert_type(contract["target"], str, "contract.target")
    _validate_engine_spec(
        contract["engine"],
        allowed_engine_member_kinds=allowed_engine_member_kinds,
        label="contract.engine",
    )


def _validate_exports_spec(
    exports: object,
    *,
    allowed_export_kinds: set[str],
    label: str,
) -> None:
    _assert_type(exports, dict, label)
    _assert_closed_keys(exports, {"mode", "names", "members"}, label)
    _require_fields(exports, {"names", "members"}, label)

    if "mode" in exports:
        _assert_equal(exports["mode"], "exact", f"{label}.mode")

    names = exports["names"]
    members = exports["members"]
    _assert_unique_strings(names, f"{label}.names")
    _assert_string_keyed_dict(members, f"{label}.members")

    member_names = list(members.keys())
    assert set(member_names) == set(names), f"{label} names and members must match exactly"

    for name, member_spec in members.items():
        _validate_export_member_spec(
            member_spec,
            allowed_export_kinds=allowed_export_kinds,
            label=f"{label}.members[{name!r}]",
        )


def _validate_engine_spec(
    engine: object,
    *,
    allowed_engine_member_kinds: set[str],
    label: str,
) -> None:
    _assert_type(engine, dict, label)
    _assert_closed_keys(engine, {"type", "public_members"}, label)
    _require_fields(engine, {"type", "public_members"}, label)
    _assert_equal(engine["type"], "Engine", f"{label}.type")

    public_members = engine["public_members"]
    _assert_type(public_members, dict, f"{label}.public_members")
    _assert_closed_keys(public_members, {"mode", "members"}, f"{label}.public_members")
    _require_fields(public_members, {"members"}, f"{label}.public_members")

    if "mode" in public_members:
        _assert_equal(public_members["mode"], "exact", f"{label}.public_members.mode")

    members = public_members["members"]
    _assert_string_keyed_dict(members, f"{label}.public_members.members")
    if len(members) != len(set(members)):
        raise AssertionError(f"{label}.public_members.members must not contain duplicates")

    for name, member_spec in members.items():
        _validate_engine_member_spec(
            member_spec,
            allowed_engine_member_kinds=allowed_engine_member_kinds,
            label=f"{label}.public_members.members[{name!r}]",
        )


def _validate_export_member_spec(
    member_spec: object,
    *,
    allowed_export_kinds: set[str],
    label: str,
) -> None:
    _assert_type(member_spec, dict, label)
    _assert_closed_keys(member_spec, {"kind", "value", "signature", "shape_probes"}, label)
    _require_fields(member_spec, {"kind"}, label)

    kind = member_spec["kind"]
    if kind not in allowed_export_kinds:
        raise AssertionError(f"{label}.kind must be one of {sorted(allowed_export_kinds)}")

    has_signature = "signature" in member_spec
    has_value = "value" in member_spec

    if kind == "callable":
        if not has_signature:
            raise AssertionError(f"{label} callable exports require signature")
    elif has_signature:
        raise AssertionError(f"{label} non-callable exports must not declare signature")

    if kind == "constant":
        if not has_value:
            raise AssertionError(f"{label} constant exports require value")
    elif has_value:
        raise AssertionError(f"{label} only constant exports may declare value")

    if has_signature:
        _validate_signature_spec(member_spec["signature"], f"{label}.signature")

    probes = member_spec.get("shape_probes", [])
    _validate_shape_probes(probes, f"{label}.shape_probes")


def _validate_engine_member_spec(
    member_spec: object,
    *,
    allowed_engine_member_kinds: set[str],
    label: str,
) -> None:
    _assert_type(member_spec, dict, label)
    _assert_closed_keys(member_spec, {"kind", "signature"}, label)
    _require_fields(member_spec, {"kind"}, label)

    kind = member_spec["kind"]
    if kind not in allowed_engine_member_kinds:
        raise AssertionError(f"{label}.kind must be one of {sorted(allowed_engine_member_kinds)}")

    has_signature = "signature" in member_spec
    if kind == "method":
        if not has_signature:
            raise AssertionError(f"{label} method members require signature")
        _validate_signature_spec(member_spec["signature"], f"{label}.signature")
        return

    if has_signature:
        raise AssertionError(f"{label} property members must not declare signature")


def _validate_signature_spec(signature: object, label: str) -> None:
    _assert_type(signature, dict, label)
    _assert_closed_keys(signature, {"params"}, label)
    _require_fields(signature, {"params"}, label)

    params = signature["params"]
    _assert_type(params, list, f"{label}.params")
    for index, param in enumerate(params):
        _validate_signature_param_spec(param, f"{label}.params[{index}]")


def _validate_signature_param_spec(param: object, label: str) -> None:
    _assert_type(param, dict, label)
    _assert_closed_keys(param, {"name", "kind", "has_default"}, label)
    _require_fields(param, {"name", "kind", "has_default"}, label)
    _assert_type(param["name"], str, f"{label}.name")
    _assert_type(param["has_default"], bool, f"{label}.has_default")
    if param["kind"] not in _SIGNATURE_PARAM_KINDS:
        raise AssertionError(f"{label}.kind must be one of {sorted(_SIGNATURE_PARAM_KINDS)}")


def _validate_shape_probes(probes: object, label: str) -> None:
    _assert_type(probes, list, label)
    for index, probe in enumerate(probes):
        _validate_shape_probe_spec(probe, f"{label}[{index}]")


def _validate_shape_probe_spec(probe: object, label: str) -> None:
    _assert_type(probe, dict, label)
    _assert_closed_keys(probe, {"args", "kwargs", "return_shape"}, label)
    _require_fields(probe, {"return_shape"}, label)

    args = probe.get("args", [])
    kwargs = probe.get("kwargs", {})
    _assert_type(args, list, f"{label}.args")
    _assert_string_keyed_dict(kwargs, f"{label}.kwargs")

    for index, value in enumerate(args):
        _validate_probe_value(value, f"{label}.args[{index}]")
    for key, value in kwargs.items():
        _validate_probe_value(value, f"{label}.kwargs[{key!r}]")

    _validate_shape_spec(probe["return_shape"], f"{label}.return_shape")


def _validate_probe_value(value: object, label: str) -> None:
    if not isinstance(value, dict) or "fixture" not in value:
        return
    _assert_closed_keys(value, {"fixture"}, label)
    _assert_equal(value["fixture"], "empty_engine", f"{label}.fixture")


def _validate_shape_spec(shape: object, label: str) -> None:
    _assert_type(shape, dict, label)
    has_kind = "kind" in shape
    has_type = "type" in shape

    if has_kind:
        kind = shape["kind"]
        if kind == "engine_instance":
            _assert_closed_keys(shape, {"kind"}, label)
            return
        if kind == "canonical_directive":
            _assert_closed_keys(shape, {"kind", "text", "directive_kind", "operands"}, label)
            _require_fields(shape, {"kind", "text", "directive_kind", "operands"}, label)
            _assert_type(shape["text"], str, f"{label}.text")
            _assert_type(shape["directive_kind"], str, f"{label}.directive_kind")
            _assert_string_keyed_dict(shape["operands"], f"{label}.operands")
            for operand_name, operand_value in shape["operands"].items():
                _assert_type(operand_value, str, f"{label}.operands[{operand_name!r}]")
            return
        raise AssertionError(f"{label}.kind has unsupported shape kind {kind!r}")

    if not has_type:
        raise AssertionError(f"{label} must declare either kind or type")

    _assert_closed_keys(shape, {"type", "const", "required_keys", "properties"}, label)
    expected_types = shape["type"]
    normalized = [expected_types] if isinstance(expected_types, str) else expected_types
    _assert_type(normalized, list, f"{label}.type")
    if not normalized:
        raise AssertionError(f"{label}.type must not be empty")
    for index, expected_type in enumerate(normalized):
        if expected_type not in _JSON_TYPES:
            raise AssertionError(f"{label}.type[{index}] must be one of {sorted(_JSON_TYPES)}")

    if ("required_keys" in shape or "properties" in shape) and "object" not in normalized:
        raise AssertionError(f"{label} only object shapes may declare required_keys/properties")

    required_keys = shape.get("required_keys", [])
    _assert_type(required_keys, list, f"{label}.required_keys")
    for index, key in enumerate(required_keys):
        _assert_type(key, str, f"{label}.required_keys[{index}]")
    if len(required_keys) != len(set(required_keys)):
        raise AssertionError(f"{label}.required_keys must not contain duplicates")

    properties = shape.get("properties", {})
    _assert_string_keyed_dict(properties, f"{label}.properties")
    for key, property_shape in properties.items():
        _validate_shape_spec(property_shape, f"{label}.properties[{key!r}]")


def _assert_type(value: object, expected_type: type[object], label: str) -> None:
    if not isinstance(value, expected_type):
        raise AssertionError(f"{label} must be a {expected_type.__name__}")


def _assert_equal(value: object, expected: object, label: str) -> None:
    if value != expected:
        raise AssertionError(f"{label} must equal {expected!r}, got {value!r}")


def _require_fields(value: dict[str, Any], required: set[str], label: str) -> None:
    missing = sorted(required - set(value))
    if missing:
        raise AssertionError(f"{label} is missing required fields: {missing}")


def _assert_closed_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise AssertionError(f"{label} has unknown fields: {unknown}")


def _assert_unique_strings(values: object, label: str) -> None:
    _assert_type(values, list, label)
    for index, value in enumerate(values):
        _assert_type(value, str, f"{label}[{index}]")
    if len(values) != len(set(values)):
        raise AssertionError(f"{label} must not contain duplicates")


def _assert_string_keyed_dict(value: object, label: str) -> None:
    _assert_type(value, dict, label)
    for key in value:
        if not isinstance(key, str):
            raise AssertionError(f"{label} keys must be strings")
