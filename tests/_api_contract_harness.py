import importlib
import inspect
import json
from pathlib import Path
from typing import Any, get_args, get_type_hints

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


def validate_declared_namespaces(
    contract: dict[str, Any],
    referenced_contracts: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Validate the explicitly declared public namespace surfaces at runtime."""
    referenced_contracts = referenced_contracts or {}
    for namespace_name, namespace_contract in contract.get("namespaces", {}).items():
        namespace = importlib.import_module(namespace_name)
        if "contract" in namespace_contract:
            reference = namespace_contract["contract"]
            if reference not in referenced_contracts:
                raise AssertionError(f"Unknown namespace contract reference {reference!r}")
            referenced = referenced_contracts[reference]
            assert referenced["id"] == reference, reference
            assert referenced["module"] == namespace_name, namespace_name
            exports = referenced["exports"]
        else:
            exports = namespace_contract["exports"]
        expected_names = exports["names"]
        assert getattr(namespace, "__all__", None) == expected_names, namespace_name

        for name, export_contract in exports["members"].items():
            exported = getattr(namespace, name)
            validate_export_kind(name, exported, export_contract["kind"])
            validate_immutable_definition(exported, export_contract, f"{namespace_name}.{name}")
            if "value" in export_contract:
                assert exported == export_contract["value"], f"{namespace_name}.{name}"
            if "signature" in export_contract and export_contract["kind"] == "callable":
                assert_signature_matches(
                    exported, export_contract["signature"], f"{namespace_name}.{name}"
                )
            for probe in export_contract.get("shape_probes", []):
                args = [resolve_probe_value(value) for value in probe.get("args", [])]
                kwargs = {
                    key: resolve_probe_value(value)
                    for key, value in probe.get("kwargs", {}).items()
                }
                result = exported(*args, **kwargs)
                assert_shape(result, probe["return_shape"], contract)
            validate_constructor_contract(
                exported, export_contract, contract, f"{namespace_name}.{name}"
            )


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
        return context_compiler.Engine()
    if fixture == "item_prohibited_failure":
        return context_compiler.SemanticFailure.ITEM_PROHIBITED
    if fixture == "use_docker_directive":
        return grammar.decompose_directive("use docker")

    raise AssertionError(f"Unknown probe fixture: {fixture!r}")


def assert_probe_raises(
    callback: Any,
    probe: dict[str, Any],
    contract: dict[str, Any] | None = None,
) -> None:
    args = [resolve_probe_value(value) for value in probe.get("args", [])]
    kwargs = {key: resolve_probe_value(value) for key, value in probe.get("kwargs", {}).items()}

    raises = probe["raises"]
    expected_exception = _resolve_exception_type(raises["type"])

    try:
        callback(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        assert isinstance(exc, expected_exception)
        if "shape" in raises:
            assert_shape(exc, raises["shape"], contract)
        return

    raise AssertionError(f"Expected {raises['type']} to be raised")


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

    if "kind" in shape and shape["kind"] == "decision_variant":
        decision_type = getattr(context_compiler, shape["type"])
        assert isinstance(value, decision_type)
        for attribute in shape["required_attributes"]:
            assert hasattr(value, attribute), attribute
        if shape["type"] == "UpdateDecision":
            assert isinstance(value.changed, bool)
        elif shape["type"] == "SemanticErrorDecision":
            assert isinstance(value.failure, context_compiler.SemanticFailure)
            assert isinstance(value.directive, grammar.CanonicalDirective)
            assert isinstance(value.repairs, tuple)
            assert all(isinstance(repair, grammar.CanonicalDirective) for repair in value.repairs)
            assert isinstance(value.message, str)
        return

    if "kind" in shape and shape["kind"] == "canonical_directive":
        assert isinstance(value, grammar.CanonicalDirective)
        assert value.text == shape["text"]
        assert value.kind.value == shape["directive_kind"]
        assert dict(value.operands) == shape["operands"]
        return

    if "kind" in shape and shape["kind"] == "directive_metadata":
        assert isinstance(value, grammar.DirectiveMetadata)
        observed_kind = (
            value.kind.value if isinstance(value.kind, grammar.DirectiveKind) else value.kind
        )
        assert observed_kind == shape["directive_kind"]
        assert value.canonical_start == shape["canonical_start"]
        assert list(value.operand_names) == shape["operand_names"]
        return

    if "kind" in shape and shape["kind"] == "invalid_directive_syntax":
        assert value == grammar.InvalidDirectiveSyntax(
            failure=grammar.DirectiveSyntaxFailure(shape["failure"]),
            directive_kind=(
                None
                if shape.get("directive_kind") is None
                else grammar.DirectiveKind(shape["directive_kind"])
            ),
            missing_operand=shape.get("missing_operand"),
        )
        return

    if "kind" in shape and shape["kind"] == "directive_metadata_collection":
        assert value == tuple(
            grammar.DirectiveMetadata(
                kind=grammar.DirectiveKind(item["directive_kind"]),
                canonical_start=item["canonical_start"],
                operand_names=tuple(item["operand_names"]),
            )
            for item in shape["items"]
        )
        return

    if "kind" in shape and shape["kind"] == "exception":
        assert isinstance(value, _resolve_exception_type(shape["type"]))
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

    expected_returns = expected.get("returns")
    if expected_returns is not None:
        actual_return = get_type_hints(obj)["return"]
        actual_types = set(get_args(actual_return) or (actual_return,))
        expected_types = {getattr(context_compiler, name) for name in expected_returns}
        assert actual_types == expected_types, label


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


def validate_constructor_contract(
    exported: object,
    export_contract: dict[str, Any],
    contract: dict[str, Any],
    label: str,
) -> None:
    if export_contract["kind"] != "class":
        return

    if "signature" not in export_contract:
        return

    assert_signature_matches(exported, export_contract["signature"], f"{label} constructor")
    for probe in export_contract.get("construction_probes", []):
        if "raises" in probe:
            assert_probe_raises(exported, probe, contract)
            continue
        args = [resolve_probe_value(value) for value in probe.get("args", [])]
        kwargs = {key: resolve_probe_value(value) for key, value in probe.get("kwargs", {}).items()}
        result = exported(*args, **kwargs)
        for field in export_contract.get("public_fields", []):
            assert hasattr(result, field), f"{label}.{field}"
        assert_shape(result, probe["return_shape"], contract)


def validate_immutable_definition(
    exported: object, export_contract: dict[str, Any], label: str
) -> None:
    if not export_contract.get("immutable_definition"):
        return

    member_values = export_contract["member_values"]
    for member_name, expected_value in member_values.items():
        member = getattr(exported, member_name)
        assert member.value == expected_value, f"{label}.{member_name} value changed"
        try:
            setattr(exported, member_name, object())
        except (AttributeError, TypeError):
            pass
        else:
            raise AssertionError(f"{label}.{member_name} can be reassigned")
        assert getattr(exported, member_name).value == expected_value, (
            f"{label}.{member_name} value changed"
        )


def _resolve_exception_type(name: str) -> type[BaseException]:
    builtins_obj = __builtins__
    namespace = builtins_obj if isinstance(builtins_obj, dict) else vars(builtins_obj)
    resolved = namespace.get(name)
    if not isinstance(resolved, type) or not issubclass(resolved, BaseException):
        raise AssertionError(f"Unsupported exception type {name!r}")
    return resolved


def validate_engine_member_runtime(
    engine_type: type[object],
    engine: object,
    name: str,
    member_contract: dict[str, Any],
) -> None:
    kind = member_contract["kind"]
    if kind == "property":
        assert isinstance(inspect.getattr_static(engine_type, name), property), name
        assert member_contract["readable"] is True, name
        getattr(engine, name)
        if member_contract["writable"] is False:
            try:
                setattr(engine, name, object())
            except (AttributeError, TypeError):
                pass
            else:
                raise AssertionError(f"{name} can be assigned")
        return
    if kind == "method":
        assert callable(getattr(engine, name)), name
        assert_signature_matches(getattr(engine, name), member_contract["signature"], name)
        return
    raise AssertionError(f"Unsupported engine member kind {kind!r} for {name}")


def validate_engine_member_probes(
    engine: object, name: str, member_contract: dict[str, Any], contract: dict[str, Any]
) -> None:
    callback = getattr(engine, name)
    for probe in member_contract.get("probes", []):
        if "raises" in probe:
            assert_probe_raises(callback, probe, contract)
            continue
        args = [resolve_probe_value(value) for value in probe.get("args", [])]
        kwargs = {key: resolve_probe_value(value) for key, value in probe.get("kwargs", {}).items()}
        result = callback(*args, **kwargs)
        assert_shape(result, probe["return_shape"], contract)


def _validate_contract(
    contract: object,
    *,
    expected_module: str,
    allowed_export_kinds: set[str],
    allowed_engine_member_kinds: set[str] | None,
) -> None:
    _assert_type(contract, dict, "contract")

    allowed_top_level = {"id", "kind", "module", "exports", "namespaces"}
    if allowed_engine_member_kinds is not None:
        allowed_top_level |= {
            "target",
            "forbidden_exports",
            "forbidden_engine_members",
            "forbidden_state_keys",
            "engine",
        }
    _assert_closed_keys(contract, allowed_top_level, "contract")

    _require_fields(contract, {"id", "kind", "module", "exports"}, "contract")
    _assert_type(contract["id"], str, "contract.id")
    _assert_equal(contract["kind"], "api-contract", "contract.kind")
    _assert_equal(contract["module"], expected_module, "contract.module")

    forbidden_exports = contract.get("forbidden_exports", [])
    _assert_type(forbidden_exports, list, "contract.forbidden_exports")
    _assert_unique_strings(forbidden_exports, "contract.forbidden_exports")

    forbidden_engine_members = contract.get("forbidden_engine_members", [])
    _assert_type(forbidden_engine_members, list, "contract.forbidden_engine_members")
    _assert_unique_strings(forbidden_engine_members, "contract.forbidden_engine_members")

    forbidden_state_keys = contract.get("forbidden_state_keys", [])
    _assert_type(forbidden_state_keys, list, "contract.forbidden_state_keys")
    _assert_unique_strings(forbidden_state_keys, "contract.forbidden_state_keys")

    exports = contract["exports"]
    _validate_exports_spec(
        exports,
        allowed_export_kinds=allowed_export_kinds,
        label="contract.exports",
    )

    namespaces = contract.get("namespaces", {})
    _validate_namespaces_spec(namespaces, allowed_export_kinds)

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


def _validate_namespaces_spec(namespaces: object, allowed_export_kinds: set[str]) -> None:
    _assert_type(namespaces, dict, "contract.namespaces")
    for namespace_name, namespace_contract in namespaces.items():
        if not isinstance(namespace_name, str) or not namespace_name:
            raise AssertionError("contract.namespaces keys must be non-empty strings")
        _assert_type(namespace_contract, dict, f"contract.namespaces[{namespace_name!r}]")
        label = f"contract.namespaces[{namespace_name!r}]"
        _assert_closed_keys(namespace_contract, {"contract", "exports"}, label)
        has_contract = "contract" in namespace_contract
        has_exports = "exports" in namespace_contract
        if has_contract == has_exports:
            raise AssertionError(f"{label} must declare exactly one of contract or exports")
        if has_contract:
            _assert_type(namespace_contract["contract"], str, f"{label}.contract")
        else:
            _validate_exports_spec(
                namespace_contract["exports"],
                allowed_export_kinds=allowed_export_kinds,
                label=f"{label}.exports",
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
    _assert_closed_keys(
        member_spec,
        {
            "kind",
            "value",
            "signature",
            "shape_probes",
            "construction_probes",
            "public_fields",
            "immutable_definition",
            "member_values",
        },
        label,
    )
    _require_fields(member_spec, {"kind"}, label)

    kind = member_spec["kind"]
    if kind not in allowed_export_kinds:
        raise AssertionError(f"{label}.kind must be one of {sorted(allowed_export_kinds)}")

    has_signature = "signature" in member_spec
    has_value = "value" in member_spec

    if kind == "callable":
        if not has_signature:
            raise AssertionError(f"{label} callable exports require signature")
    elif kind != "class" and has_signature:
        raise AssertionError(f"{label} non-callable exports must not declare signature")

    if kind == "constant":
        if not has_value:
            raise AssertionError(f"{label} constant exports require value")
    elif has_value:
        raise AssertionError(f"{label} only constant exports may declare value")

    if has_signature:
        _validate_signature_spec(member_spec["signature"], f"{label}.signature")

    if "public_fields" in member_spec:
        _assert_unique_strings(member_spec["public_fields"], f"{label}.public_fields")
        if kind != "class":
            raise AssertionError(f"{label}.public_fields only applies to class exports")

    immutable = member_spec.get("immutable_definition", False)
    if not isinstance(immutable, bool):
        raise AssertionError(f"{label}.immutable_definition must be boolean")
    if immutable:
        if kind != "class":
            raise AssertionError(f"{label}.immutable_definition only applies to class exports")
        member_values = member_spec.get("member_values")
        _assert_type(member_values, dict, f"{label}.member_values")
        _assert_string_keyed_dict(member_values, f"{label}.member_values")
    elif "member_values" in member_spec:
        raise AssertionError(f"{label}.member_values requires immutable_definition")

    probes = member_spec.get("shape_probes", [])
    _validate_shape_probes(probes, f"{label}.shape_probes")

    construction_probes = member_spec.get("construction_probes", [])
    if kind != "class" and construction_probes:
        raise AssertionError(f"{label} only class exports may declare construction_probes")
    _validate_construction_probes(construction_probes, f"{label}.construction_probes")


def _validate_engine_member_spec(
    member_spec: object,
    *,
    allowed_engine_member_kinds: set[str],
    label: str,
) -> None:
    _assert_type(member_spec, dict, label)
    _assert_closed_keys(member_spec, {"kind", "signature", "probes", "readable", "writable"}, label)
    _require_fields(member_spec, {"kind"}, label)

    kind = member_spec["kind"]
    if kind not in allowed_engine_member_kinds:
        raise AssertionError(f"{label}.kind must be one of {sorted(allowed_engine_member_kinds)}")

    has_signature = "signature" in member_spec
    if kind == "method":
        if "readable" in member_spec or "writable" in member_spec:
            raise AssertionError(f"{label} method members must not declare property mutability")
        if not has_signature:
            raise AssertionError(f"{label} method members require signature")
        _validate_signature_spec(member_spec["signature"], f"{label}.signature")
        _validate_construction_probes(member_spec.get("probes", []), f"{label}.probes")
        return

    if has_signature:
        raise AssertionError(f"{label} property members must not declare signature")
    if "probes" in member_spec:
        raise AssertionError(f"{label} property members must not declare probes")
    for field in ("readable", "writable"):
        if field not in member_spec or not isinstance(member_spec[field], bool):
            raise AssertionError(f"{label}.{field} must be boolean")


def _validate_signature_spec(signature: object, label: str) -> None:
    _assert_type(signature, dict, label)
    _assert_closed_keys(signature, {"params", "returns"}, label)
    _require_fields(signature, {"params"}, label)

    params = signature["params"]
    _assert_type(params, list, f"{label}.params")
    for index, param in enumerate(params):
        _validate_signature_param_spec(param, f"{label}.params[{index}]")

    if "returns" in signature:
        returns = signature["returns"]
        _assert_type(returns, list, f"{label}.returns")
        for index, return_type in enumerate(returns):
            _assert_type(return_type, str, f"{label}.returns[{index}]")


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


def _validate_construction_probes(probes: object, label: str) -> None:
    _assert_type(probes, list, label)
    for index, probe in enumerate(probes):
        _validate_construction_probe_spec(probe, f"{label}[{index}]")


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


def _validate_construction_probe_spec(probe: object, label: str) -> None:
    _assert_type(probe, dict, label)
    _assert_closed_keys(probe, {"args", "kwargs", "return_shape", "raises"}, label)

    has_return = "return_shape" in probe
    has_raises = "raises" in probe
    if has_return == has_raises:
        raise AssertionError(f"{label} must declare exactly one of return_shape or raises")

    args = probe.get("args", [])
    kwargs = probe.get("kwargs", {})
    _assert_type(args, list, f"{label}.args")
    _assert_string_keyed_dict(kwargs, f"{label}.kwargs")

    for index, value in enumerate(args):
        _validate_probe_value(value, f"{label}.args[{index}]")
    for key, value in kwargs.items():
        _validate_probe_value(value, f"{label}.kwargs[{key!r}]")

    if has_return:
        _validate_shape_spec(probe["return_shape"], f"{label}.return_shape")
        return

    _validate_exception_shape_spec(probe["raises"], f"{label}.raises")


def _validate_probe_value(value: object, label: str) -> None:
    if not isinstance(value, dict) or "fixture" not in value:
        return
    _assert_closed_keys(value, {"fixture"}, label)
    if value["fixture"] not in {
        "empty_engine",
        "item_prohibited_failure",
        "use_docker_directive",
    }:
        raise AssertionError(f"Unknown probe fixture: {value['fixture']!r}")


def _validate_exception_shape_spec(raises: object, label: str) -> None:
    _assert_type(raises, dict, label)
    _assert_closed_keys(raises, {"type", "shape"}, label)
    _require_fields(raises, {"type"}, label)
    _assert_type(raises["type"], str, f"{label}.type")
    _resolve_exception_type(raises["type"])
    if "shape" in raises:
        _validate_shape_spec(raises["shape"], f"{label}.shape")


def _validate_shape_spec(shape: object, label: str) -> None:
    _assert_type(shape, dict, label)
    has_kind = "kind" in shape
    has_type = "type" in shape

    if has_kind:
        kind = shape["kind"]
        if kind == "engine_instance":
            _assert_closed_keys(shape, {"kind"}, label)
            return
        if kind == "decision_variant":
            _assert_closed_keys(shape, {"kind", "type", "required_attributes"}, label)
            _require_fields(shape, {"kind", "type", "required_attributes"}, label)
            _assert_type(shape["type"], str, f"{label}.type")
            required_attributes = shape["required_attributes"]
            _assert_type(required_attributes, list, f"{label}.required_attributes")
            for index, attribute in enumerate(required_attributes):
                _assert_type(attribute, str, f"{label}.required_attributes[{index}]")
            getattr(context_compiler, shape["type"])
            for attribute in required_attributes:
                _assert_type(attribute, str, f"{label}.{attribute}")
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
        if kind == "directive_metadata":
            _assert_closed_keys(
                shape,
                {"kind", "directive_kind", "canonical_start", "operand_names"},
                label,
            )
            _require_fields(
                shape,
                {"kind", "directive_kind", "canonical_start", "operand_names"},
                label,
            )
            _assert_type(shape["directive_kind"], str, f"{label}.directive_kind")
            _assert_type(shape["canonical_start"], str, f"{label}.canonical_start")
            _assert_type(shape["operand_names"], list, f"{label}.operand_names")
            for index, operand_name in enumerate(shape["operand_names"]):
                _assert_type(operand_name, str, f"{label}.operand_names[{index}]")
            return
        if kind == "invalid_directive_syntax":
            _assert_closed_keys(
                shape,
                {"kind", "failure", "directive_kind", "missing_operand"},
                label,
            )
            _require_fields(
                shape,
                {"kind", "failure", "directive_kind", "missing_operand"},
                label,
            )
            _assert_type(shape["failure"], str, f"{label}.failure")
            if "directive_kind" in shape and shape["directive_kind"] is not None:
                _assert_type(shape["directive_kind"], str, f"{label}.directive_kind")
            if "missing_operand" in shape and shape["missing_operand"] is not None:
                _assert_type(shape["missing_operand"], str, f"{label}.missing_operand")
            return
        if kind == "directive_metadata_collection":
            _assert_closed_keys(shape, {"kind", "items"}, label)
            _require_fields(shape, {"kind", "items"}, label)
            items = shape["items"]
            _assert_type(items, list, f"{label}.items")
            for index, item in enumerate(items):
                item_label = f"{label}.items[{index}]"
                _assert_type(item, dict, item_label)
                _assert_closed_keys(
                    item,
                    {"directive_kind", "canonical_start", "operand_names"},
                    item_label,
                )
                _require_fields(
                    item,
                    {"directive_kind", "canonical_start", "operand_names"},
                    item_label,
                )
                _assert_type(item["directive_kind"], str, f"{item_label}.directive_kind")
                _assert_type(item["canonical_start"], str, f"{item_label}.canonical_start")
                operand_names = item["operand_names"]
                _assert_type(operand_names, list, f"{item_label}.operand_names")
                for operand_index, operand_name in enumerate(operand_names):
                    _assert_type(
                        operand_name,
                        str,
                        f"{item_label}.operand_names[{operand_index}]",
                    )
            return
        if kind == "exception":
            _assert_closed_keys(shape, {"kind", "type"}, label)
            _require_fields(shape, {"kind", "type"}, label)
            _assert_type(shape["type"], str, f"{label}.type")
            _resolve_exception_type(shape["type"])
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
