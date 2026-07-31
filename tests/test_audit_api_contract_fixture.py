from pathlib import Path

from _api_contract_harness import (
    assert_shape,
    assert_signature_matches,
    load_api_contract,
    resolve_probe_value,
    validate_export_kind,
)

import context_compiler.audit as audit

_CONTRACT_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "api" / "public-audit-v1.json"
)


def _load_contract() -> dict[str, object]:
    return load_api_contract(
        _CONTRACT_PATH,
        expected_module="context_compiler.audit",
        allowed_export_kinds={"callable", "type"},
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
        validate_export_kind(name, exported, member["kind"])
        if member["kind"] == "callable":
            assert_signature_matches(exported, member["signature"], name)
            for probe in member.get("shape_probes", []):
                args = [resolve_probe_value(value) for value in probe.get("args", [])]
                kwargs = {
                    key: resolve_probe_value(value)
                    for key, value in probe.get("kwargs", {}).items()
                }
                result = exported(*args, **kwargs)
                assert_shape(result, probe["return_shape"])
