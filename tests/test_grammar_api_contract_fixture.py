from pathlib import Path

from _api_contract_harness import (
    assert_probe_raises,
    assert_shape,
    assert_signature_matches,
    load_api_contract,
    validate_export_kind,
)

import context_compiler.grammar as grammar

_CONTRACT_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "api" / "public-grammar-v1.json"
)


def _load_contract() -> dict[str, object]:
    return load_api_contract(
        _CONTRACT_PATH,
        expected_module="context_compiler.grammar",
        allowed_export_kinds={"callable", "class"},
    )


def test_public_grammar_contract_matches_surface() -> None:
    contract = _load_contract()

    exports = contract["exports"]
    expected_names = exports["names"]
    members = exports["members"]

    actual_names = sorted(name for name in grammar.__all__)
    assert actual_names == sorted(expected_names)

    for name in expected_names:
        assert hasattr(grammar, name), name

    for name, member in members.items():
        exported = getattr(grammar, name)
        validate_export_kind(name, exported, member["kind"])
        if member["kind"] == "callable":
            assert_signature_matches(exported, member["signature"], name)
            for probe in member.get("shape_probes", []):
                result = exported(*probe.get("args", []), **probe.get("kwargs", {}))
                assert_shape(result, probe["return_shape"])
        if member["kind"] == "class":
            for probe in member.get("construction_probes", []):
                if "raises" in probe:
                    assert_probe_raises(exported, probe)
                    continue
                result = exported(*probe.get("args", []), **probe.get("kwargs", {}))
                assert_shape(result, probe["return_shape"])


def test_public_grammar_contract_has_unique_entries() -> None:
    contract = _load_contract()
    export_names = contract["exports"]["names"]
    members = contract["exports"]["members"]

    assert len(export_names) == len(set(export_names))
    assert set(members) == set(export_names)
