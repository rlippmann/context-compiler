import json
from copy import deepcopy
from pathlib import Path

import pytest

from context_compiler import DECISION_ERROR, DECISION_UPDATE, create_engine, get_decision_state
from context_compiler.controller import get_step_state, preview, state_diff, step
from context_compiler.grammar import (
    DirectiveKind,
    decompose_directive,
    render_directive,
    validate_directive,
)

_STEP_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "conformance" / "step"
_STATE_JSON_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "state-json"
)
_CONTROLLER_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "controller"
)
_GRAMMAR_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "conformance" / "grammar"
_MUTATION_ISOLATION_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "mutation-isolation"
)
_MUTATION_ISOLATION_HANDLE_KINDS = {
    "caller_owned_input",
    "defensive_snapshot",
    "independently_constructed_result",
    "nested_state_member",
    "caller_owned_result_envelope",
    "caller_owned_nested_member",
}
_DIRECT_HANDLE_KINDS = {
    "caller_owned_input",
    "defensive_snapshot",
    "independently_constructed_result",
    "caller_owned_result_envelope",
    "caller_owned_nested_member",
}
_DERIVED_HANDLE_KINDS = {"nested_state_member", "defensive_snapshot"}


def _json_files(dir_path: Path) -> list[Path]:
    return sorted(dir_path.glob("*.json"))


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_fixture_path_matches_id(path: Path, fixture_id: object) -> None:
    assert path.stem == fixture_id, f"{fixture_id}: filename/id mismatch"


def _assert_allowed_keys(
    obj: dict[str, object], allowed_keys: set[str], fixture_id: object, label: str
) -> None:
    assert set(obj) == allowed_keys, f"{fixture_id}: invalid keys for {label}"


def _assert_str_list(value: object, fixture_id: object, label: str) -> None:
    assert isinstance(value, list), f"{fixture_id}: invalid {label}"
    assert all(isinstance(item, str) for item in value), f"{fixture_id}: invalid {label}"


def _validate_step_fixture(fixture: dict[str, object], fixture_id: object) -> None:
    _assert_allowed_keys(
        fixture,
        {"id", "kind", "initial_state", "input", "expected"} | ({"prelude"} & set(fixture)),
        fixture_id,
        "fixture",
    )
    assert fixture["kind"] == "step", fixture_id
    assert isinstance(fixture["input"], str), fixture_id
    assert isinstance(fixture["initial_state"], dict), fixture_id
    if "prelude" in fixture:
        _assert_str_list(fixture["prelude"], fixture_id, "prelude")

    expected = fixture["expected"]
    assert isinstance(expected, dict), fixture_id
    _assert_allowed_keys(expected, {"decision", "state"}, fixture_id, "expected")
    assert isinstance(expected["state"], dict), fixture_id

    decision = expected["decision"]
    assert isinstance(decision, dict), fixture_id
    _validate_public_decision(decision, fixture_id, "expected.decision")


def _validate_state_json_fixture(fixture: dict[str, object], fixture_id: object) -> None:
    _assert_allowed_keys(
        fixture,
        {"id", "kind", "initial_state", "action", "expected"} | ({"prelude"} & set(fixture)),
        fixture_id,
        "fixture",
    )
    assert fixture["kind"] == "state_json", fixture_id
    assert isinstance(fixture["initial_state"], dict), fixture_id
    if "prelude" in fixture:
        _assert_str_list(fixture["prelude"], fixture_id, "prelude")

    action = fixture["action"]
    assert isinstance(action, dict), fixture_id
    fn = action["fn"]
    assert fn in {"export_json", "import_json"}, fixture_id
    if fn == "export_json":
        _assert_allowed_keys(action, {"fn"}, fixture_id, "action")
    else:
        assert fn == "import_json", fixture_id
        _assert_allowed_keys(action, {"fn", "payload"}, fixture_id, "action")
        assert isinstance(action["payload"], str), fixture_id

    expected = fixture["expected"]
    assert isinstance(expected, dict), fixture_id
    if "error" in expected:
        _assert_allowed_keys(expected, {"error", "state"}, fixture_id, "expected")
        error = expected["error"]
        assert isinstance(error, dict), fixture_id
        _assert_allowed_keys(error, {"type", "message_contains"}, fixture_id, "expected.error")
        assert isinstance(error["type"], str), fixture_id
        assert isinstance(error["message_contains"], str), fixture_id
    elif fn == "export_json":
        _assert_allowed_keys(expected, {"payload", "state"}, fixture_id, "expected")
        assert isinstance(expected["payload"], str), fixture_id
    else:
        _assert_allowed_keys(expected, {"state"}, fixture_id, "expected")
    assert isinstance(expected["state"], dict), fixture_id


def _validate_controller_result_decision(decision: object, fixture_id: object, label: str) -> None:
    assert isinstance(decision, dict), fixture_id
    _validate_public_decision(decision, fixture_id, label)


def _validate_public_decision(decision: dict[str, object], fixture_id: object, label: str) -> None:
    _assert_allowed_keys(
        decision,
        {"kind"} | ({"state"} & set(decision)) | ({"message"} & set(decision)),
        fixture_id,
        label,
    )
    kind = decision.get("kind")
    assert isinstance(kind, str), fixture_id

    if kind == "no_directive":
        _assert_allowed_keys(decision, {"kind"}, fixture_id, label)
        return
    if kind == "update":
        _assert_allowed_keys(decision, {"kind", "state"}, fixture_id, label)
        assert isinstance(decision["state"], dict), fixture_id
        return

    assert kind == "error", fixture_id
    _assert_allowed_keys(decision, {"kind", "message"}, fixture_id, label)
    assert isinstance(decision["message"], str), fixture_id


def _validate_controller_diff(diff: object, fixture_id: object, label: str) -> None:
    assert isinstance(diff, dict), fixture_id
    _assert_allowed_keys(diff, {"changed", "premise", "policies"}, fixture_id, label)
    assert isinstance(diff["changed"], bool), fixture_id

    premise = diff["premise"]
    assert isinstance(premise, dict), fixture_id
    _assert_allowed_keys(premise, {"before", "after", "changed"}, fixture_id, f"{label}.premise")
    assert isinstance(premise["changed"], bool), fixture_id

    policies = diff["policies"]
    assert isinstance(policies, dict), fixture_id
    _assert_allowed_keys(policies, {"added", "removed", "changed"}, fixture_id, f"{label}.policies")
    assert isinstance(policies["added"], dict), fixture_id
    assert isinstance(policies["removed"], dict), fixture_id
    assert isinstance(policies["changed"], dict), fixture_id
    for policy_change in policies["changed"].values():
        assert isinstance(policy_change, dict), fixture_id
        _assert_allowed_keys(
            policy_change, {"before", "after"}, fixture_id, f"{label}.policies.changed"
        )


def _validate_controller_fixture(fixture: dict[str, object], fixture_id: object) -> None:
    _assert_allowed_keys(
        fixture,
        {"id", "kind", "initial_state", "action", "expected"} | ({"prelude"} & set(fixture)),
        fixture_id,
        "fixture",
    )
    assert fixture["kind"] == "controller", fixture_id
    assert isinstance(fixture["initial_state"], dict), fixture_id
    if "prelude" in fixture:
        _assert_str_list(fixture["prelude"], fixture_id, "prelude")

    action = fixture["action"]
    assert isinstance(action, dict), fixture_id
    fn = action["fn"]
    assert fn in {"step", "preview", "state_diff"}, fixture_id
    expected = fixture["expected"]
    assert isinstance(expected, dict), fixture_id

    if fn == "step":
        _assert_allowed_keys(action, {"fn", "input"}, fixture_id, "action")
        assert isinstance(action["input"], str), fixture_id
        _assert_allowed_keys(expected, {"result", "state"}, fixture_id, "expected")
        assert isinstance(expected["state"], dict), fixture_id
        result = expected["result"]
        assert isinstance(result, dict), fixture_id
        _assert_allowed_keys(
            result, {"output_version", "mode", "decision", "state"}, fixture_id, "expected.result"
        )
        _validate_controller_result_decision(
            result["decision"], fixture_id, "expected.result.decision"
        )
        assert isinstance(result["state"], dict), fixture_id
    elif fn == "preview":
        _assert_allowed_keys(action, {"fn", "input"}, fixture_id, "action")
        assert isinstance(action["input"], str), fixture_id
        _assert_allowed_keys(expected, {"result", "state_after_preview"}, fixture_id, "expected")
        assert isinstance(expected["state_after_preview"], dict), fixture_id
        result = expected["result"]
        assert isinstance(result, dict), fixture_id
        _assert_allowed_keys(
            result,
            {
                "output_version",
                "mode",
                "decision",
                "state_before",
                "state_after",
                "diff",
                "would_mutate",
            },
            fixture_id,
            "expected.result",
        )
        _validate_controller_result_decision(
            result["decision"], fixture_id, "expected.result.decision"
        )
        assert isinstance(result["state_before"], dict), fixture_id
        assert isinstance(result["state_after"], dict), fixture_id
        _validate_controller_diff(result["diff"], fixture_id, "expected.result.diff")
        assert isinstance(result["would_mutate"], bool), fixture_id
    else:
        assert fn == "state_diff", fixture_id
        _assert_allowed_keys(action, {"fn", "before", "after"}, fixture_id, "action")
        assert isinstance(action["before"], dict), fixture_id
        assert isinstance(action["after"], dict), fixture_id
        _assert_allowed_keys(expected, {"diff"}, fixture_id, "expected")
        _validate_controller_diff(expected["diff"], fixture_id, "expected.diff")


def _validate_grammar_fixture(fixture: dict[str, object], fixture_id: object) -> None:
    _assert_allowed_keys(fixture, {"id", "kind", "action", "expected"}, fixture_id, "fixture")
    assert fixture["kind"] == "grammar", fixture_id

    action = fixture["action"]
    assert isinstance(action, dict), fixture_id
    expected = fixture["expected"]
    assert isinstance(expected, dict), fixture_id
    fn = action["fn"]
    assert fn in {"decompose_directive", "validate_directive", "render_directive"}, fixture_id

    if fn == "decompose_directive":
        _assert_allowed_keys(action, {"fn", "text"}, fixture_id, "action")
        assert isinstance(action["text"], str), fixture_id
        _assert_allowed_keys(expected, {"directive"}, fixture_id, "expected")
        directive = expected["directive"]
        if directive is not None:
            assert isinstance(directive, dict), fixture_id
            _assert_allowed_keys(
                directive, {"text", "kind", "operands"}, fixture_id, "expected.directive"
            )
            assert isinstance(directive["text"], str), fixture_id
            assert isinstance(directive["kind"], str), fixture_id
            assert isinstance(directive["operands"], dict), fixture_id
            assert all(isinstance(key, str) for key in directive["operands"]), fixture_id
            assert all(isinstance(value, str) for value in directive["operands"].values()), (
                fixture_id
            )
    elif fn == "validate_directive":
        _assert_allowed_keys(action, {"fn", "text"}, fixture_id, "action")
        assert isinstance(action["text"], str), fixture_id
        _assert_allowed_keys(expected, {"validated"}, fixture_id, "expected")
        validated = expected["validated"]
        if validated is not None:
            assert isinstance(validated, dict), fixture_id
            _assert_allowed_keys(validated, {"text", "kind"}, fixture_id, "expected.validated")
            assert isinstance(validated["text"], str), fixture_id
            assert isinstance(validated["kind"], str), fixture_id
    else:
        assert fn == "render_directive", fixture_id
        _assert_allowed_keys(action, {"fn", "kind", "operands"}, fixture_id, "action")
        assert isinstance(action["kind"], str), fixture_id
        assert isinstance(action["operands"], dict), fixture_id
        _assert_allowed_keys(expected, {"text", "validated_kind"}, fixture_id, "expected")
        assert isinstance(expected["text"], str), fixture_id
        assert isinstance(expected["validated_kind"], str), fixture_id


def _get_path_value(obj: object, path: list[object]) -> object:
    current = obj
    for key in path:
        assert isinstance(current, dict)
        assert isinstance(key, str)
        current = current[key]
    return current


def _set_path_value(obj: object, path: list[object], value: object) -> None:
    assert path
    current = obj
    for key in path[:-1]:
        assert isinstance(current, dict)
        assert isinstance(key, str)
        current = current[key]
    assert isinstance(current, dict)
    final_key = path[-1]
    assert isinstance(final_key, str)
    current[final_key] = value


def test_step_fixtures() -> None:
    for path in _json_files(_STEP_FIXTURES_DIR):
        fixture = _load(path)
        fixture_id = fixture["id"]

        _assert_fixture_path_matches_id(path, fixture_id)
        _validate_step_fixture(fixture, fixture_id)
        assert fixture["kind"] == "step", fixture_id

        engine = create_engine(state=fixture["initial_state"])
        prelude = fixture.get("prelude", [])
        for prior_input in prelude:
            engine.step(prior_input)
        decision = engine.step(fixture["input"])

        expected = fixture["expected"]
        expected_decision = expected["decision"]

        assert decision["kind"] == expected_decision["kind"], fixture_id

        if decision["kind"] == DECISION_ERROR:
            expected_message = expected_decision.get("message")
            actual_message = decision["message"]
            if expected_message is None:
                assert actual_message != "", fixture_id
            else:
                assert actual_message == expected_message, fixture_id
        else:
            assert decision == expected_decision, fixture_id

        if decision["kind"] == DECISION_UPDATE:
            assert decision["state"] == engine.state, fixture_id

        assert engine.state == expected["state"], fixture_id


def _apply_prelude(engine: object, prelude: object) -> None:
    assert isinstance(prelude, list)
    for prior_input in prelude:
        assert isinstance(prior_input, str)
        engine.step(prior_input)


def test_state_json_fixtures() -> None:
    for path in _json_files(_STATE_JSON_FIXTURES_DIR):
        fixture = _load(path)
        fixture_id = fixture["id"]

        _assert_fixture_path_matches_id(path, fixture_id)
        _validate_state_json_fixture(fixture, fixture_id)
        assert fixture["kind"] == "state_json", fixture_id
        engine = create_engine(state=fixture["initial_state"])
        _apply_prelude(engine, fixture.get("prelude", []))

        action = fixture["action"]
        expected = fixture["expected"]
        fn = action["fn"]

        if fn == "export_json":
            payload = engine.export_json()
            assert payload == expected["payload"], fixture_id
        elif fn == "import_json":
            payload = action["payload"]
            error = expected.get("error")
            if error is None:
                engine.import_json(payload)
            else:
                expected_error_type = error["type"]
                with pytest.raises(Exception, match=error["message_contains"]) as exc_info:
                    engine.import_json(payload)
                assert type(exc_info.value).__name__ == expected_error_type, fixture_id
        else:
            raise AssertionError(f"Unknown state_json action: {fn}")

        assert engine.state == expected["state"], fixture_id


def test_controller_fixtures() -> None:
    for path in _json_files(_CONTROLLER_FIXTURES_DIR):
        fixture = _load(path)
        fixture_id = fixture["id"]

        _assert_fixture_path_matches_id(path, fixture_id)
        _validate_controller_fixture(fixture, fixture_id)
        assert fixture["kind"] == "controller", fixture_id
        engine = create_engine(state=fixture["initial_state"])
        _apply_prelude(engine, fixture.get("prelude", []))

        action = fixture["action"]
        expected = fixture["expected"]
        fn = action["fn"]

        if fn == "step":
            result = step(engine, action["input"])
            assert result == expected["result"], fixture_id
            assert engine.state == expected["state"], fixture_id
            continue

        elif fn == "preview":
            before = engine.state
            result = preview(engine, action["input"])

            assert result == expected["result"], fixture_id
            assert engine.state == before, fixture_id
            assert engine.state == expected["state_after_preview"], fixture_id
        elif fn == "state_diff":
            diff = state_diff(action["before"], action["after"])
            assert diff == expected["diff"], fixture_id
        else:
            raise AssertionError(f"Unknown controller action: {fn}")


def test_grammar_fixtures() -> None:
    for path in _json_files(_GRAMMAR_FIXTURES_DIR):
        fixture = _load(path)
        fixture_id = fixture["id"]

        _assert_fixture_path_matches_id(path, fixture_id)
        _validate_grammar_fixture(fixture, fixture_id)
        assert fixture["kind"] == "grammar", fixture_id
        action = fixture["action"]
        expected = fixture["expected"]
        fn = action["fn"]

        if fn == "decompose_directive":
            directive = decompose_directive(action["text"])
            expected_directive = expected["directive"]
            if expected_directive is None:
                assert directive is None, fixture_id
            else:
                assert directive is not None, fixture_id
                assert directive.text == expected_directive["text"], fixture_id
                assert directive.kind.value == expected_directive["kind"], fixture_id
                assert dict(directive.operands) == expected_directive["operands"], fixture_id
        elif fn == "validate_directive":
            validated = validate_directive(action["text"])
            expected_validated = expected["validated"]
            if expected_validated is None:
                assert validated is None, fixture_id
            else:
                assert validated is not None, fixture_id
                assert validated.text == expected_validated["text"], fixture_id
                assert validated.kind.value == expected_validated["kind"], fixture_id
        elif fn == "render_directive":
            rendered = render_directive(DirectiveKind(action["kind"]), **action["operands"])
            assert rendered == expected["text"], fixture_id
            validated = validate_directive(rendered)
            assert validated is not None, fixture_id
            assert validated.kind.value == expected["validated_kind"], fixture_id
        else:
            raise AssertionError(f"Unknown grammar action: {fn}")


def _validate_mutation_isolation_fixture(fixture: dict[str, object], fixture_id: object) -> None:
    _assert_allowed_keys(
        fixture,
        {"id", "kind", "initial_state", "operation", "handles", "mutations", "expected"},
        fixture_id,
        "fixture",
    )
    assert fixture["kind"] == "mutation_isolation", fixture_id
    assert isinstance(fixture["initial_state"], dict), fixture_id

    operation = fixture["operation"]
    assert isinstance(operation, dict), fixture_id
    fn = operation["fn"]
    assert fn in {
        "create_engine",
        "engine.policies",
        "engine.premise",
        "engine.state",
        "engine.step",
        "controller.step",
        "controller.preview",
        "get_decision_state",
        "get_step_state",
    }, fixture_id
    assert all(isinstance(key, str) for key in operation), fixture_id

    handles = fixture["handles"]
    assert isinstance(handles, dict), fixture_id
    for handle_name, handle_spec in handles.items():
        assert isinstance(handle_name, str), fixture_id
        assert isinstance(handle_spec, dict), fixture_id
        assert handle_spec["kind"] in _MUTATION_ISOLATION_HANDLE_KINDS, fixture_id
        if "from_handle" in handle_spec or "path" in handle_spec:
            _assert_allowed_keys(
                handle_spec, {"kind", "from_handle", "path"}, fixture_id, f"handle {handle_name}"
            )
            assert handle_spec["kind"] in _DERIVED_HANDLE_KINDS, fixture_id
            assert isinstance(handle_spec["from_handle"], str), fixture_id
            assert handle_spec["from_handle"] in handles, fixture_id
            assert isinstance(handle_spec["path"], list), fixture_id
            assert handle_spec["path"], fixture_id
            assert all(isinstance(part, str) for part in handle_spec["path"]), fixture_id
        else:
            allowed_keys = (
                {"kind", "value"} if handle_spec["kind"] == "caller_owned_input" else {"kind"}
            )
            _assert_allowed_keys(handle_spec, allowed_keys, fixture_id, f"handle {handle_name}")
            assert handle_spec["kind"] in _DIRECT_HANDLE_KINDS, fixture_id

    if fn == "create_engine":
        assert set(operation) == {"fn", "constructor_state_handle"}, fixture_id
        constructor_state_handle = operation["constructor_state_handle"]
        assert isinstance(constructor_state_handle, str), fixture_id
        assert constructor_state_handle in handles, fixture_id
        constructor_state_spec = handles[constructor_state_handle]
        assert constructor_state_spec["kind"] == "caller_owned_input", fixture_id
        assert set(constructor_state_spec) == {"kind", "value"}, fixture_id
        assert constructor_state_spec["value"] == fixture["initial_state"], fixture_id
    elif fn == "engine.state" or fn in {"engine.policies", "engine.premise"}:
        assert set(operation) == {"fn", "result_handle"}, fixture_id
        result_handle = operation["result_handle"]
        assert isinstance(result_handle, str), fixture_id
        assert result_handle in handles, fixture_id
        assert handles[result_handle]["kind"] == "defensive_snapshot", fixture_id
    elif fn in {"engine.step", "controller.step", "controller.preview"}:
        assert set(operation) == {"fn", "input", "result_handle"}, fixture_id
        assert isinstance(operation["input"], str), fixture_id
        result_handle = operation["result_handle"]
        assert isinstance(result_handle, str), fixture_id
        assert result_handle in handles, fixture_id
        expected_result_kind = (
            "independently_constructed_result"
            if fn == "engine.step"
            else "caller_owned_result_envelope"
        )
        assert handles[result_handle]["kind"] == expected_result_kind, fixture_id
    else:
        assert fn in {"get_decision_state", "get_step_state"}, fixture_id
        assert set(operation) == {"fn", "input", "result_handle", "source_handle"}, fixture_id
        assert isinstance(operation["input"], str), fixture_id
        result_handle = operation["result_handle"]
        source_handle = operation["source_handle"]
        assert isinstance(result_handle, str), fixture_id
        assert isinstance(source_handle, str), fixture_id
        assert result_handle in handles, fixture_id
        assert source_handle in handles, fixture_id
        assert handles[result_handle]["kind"] == "caller_owned_nested_member", fixture_id
        expected_source_kind = (
            "independently_constructed_result"
            if fn == "get_decision_state"
            else "caller_owned_result_envelope"
        )
        assert handles[source_handle]["kind"] == expected_source_kind, fixture_id

    for _handle_name, handle_spec in handles.items():
        from_handle = handle_spec.get("from_handle")
        if from_handle is None:
            continue
        assert isinstance(from_handle, str), fixture_id
        source_kind = handles[from_handle]["kind"]
        derived_kind = handle_spec["kind"]
        if derived_kind == "nested_state_member":
            assert source_kind == "independently_constructed_result", fixture_id
            assert handle_spec["path"] == ["state"], fixture_id
        else:
            assert derived_kind == "defensive_snapshot", fixture_id
            assert source_kind == "caller_owned_result_envelope", fixture_id
            assert handle_spec["path"] in (["state_before"], ["state_after"]), fixture_id

    mutations = fixture["mutations"]
    assert isinstance(mutations, list), fixture_id
    for mutation in mutations:
        assert isinstance(mutation, dict), fixture_id
        assert set(mutation) == {"target_handle", "path", "op", "value"}, fixture_id
        assert mutation["target_handle"] in handles, fixture_id
        assert mutation["op"] == "set", fixture_id
        assert isinstance(mutation["path"], list), fixture_id
        assert mutation["path"], fixture_id
        assert all(isinstance(part, str) for part in mutation["path"]), fixture_id

    expected = fixture["expected"]
    assert isinstance(expected, dict), fixture_id
    _assert_allowed_keys(
        expected,
        {"authoritative_state"}
        | (
            {
                "preview_live_state_unchanged",
                "identity_assertions",
                "caller_owned_observations",
            }
            & set(expected.keys())
        ),
        fixture_id,
        "expected",
    )
    assert isinstance(expected["authoritative_state"], dict), fixture_id
    if "preview_live_state_unchanged" in expected:
        assert fn == "controller.preview", fixture_id
        assert expected["preview_live_state_unchanged"] is True, fixture_id

    identity_assertions = expected.get("identity_assertions", [])
    assert isinstance(identity_assertions, list), fixture_id
    for assertion in identity_assertions:
        assert isinstance(assertion, dict), fixture_id
        assert set(assertion) == {"left_handle", "right_handle", "right_path", "same_identity"}, (
            fixture_id
        )
        assert assertion["left_handle"] in handles, fixture_id
        assert assertion["right_handle"] in handles, fixture_id
        assert isinstance(assertion["right_path"], list), fixture_id
        assert assertion["right_path"], fixture_id
        assert all(isinstance(part, str) for part in assertion["right_path"]), fixture_id
        assert isinstance(assertion["same_identity"], bool), fixture_id

    caller_owned_observations = expected.get("caller_owned_observations", [])
    assert isinstance(caller_owned_observations, list), fixture_id
    for observation in caller_owned_observations:
        assert isinstance(observation, dict), fixture_id
        assert set(observation) == {"handle", "path", "value"}, fixture_id
        assert observation["handle"] in handles, fixture_id
        assert isinstance(observation["path"], list), fixture_id
        assert observation["path"], fixture_id
        assert all(isinstance(part, str) for part in observation["path"]), fixture_id


def test_mutation_isolation_validator_rejects_unknown_top_level_field() -> None:
    fixture = {
        "id": "invalid_unknown_top_level",
        "kind": "mutation_isolation",
        "initial_state": {"premise": None, "policies": {}, "version": 2},
        "operation": {"fn": "engine.state", "result_handle": "state_snapshot"},
        "handles": {"state_snapshot": {"kind": "defensive_snapshot"}},
        "mutations": [
            {
                "target_handle": "state_snapshot",
                "path": ["premise"],
                "op": "set",
                "value": "mutated",
            }
        ],
        "expected": {"authoritative_state": {"premise": None, "policies": {}, "version": 2}},
        "unexpected": True,
    }

    with pytest.raises(AssertionError):
        _validate_mutation_isolation_fixture(fixture, fixture["id"])


def test_step_validator_rejects_unknown_expected_decision_field() -> None:
    fixture = {
        "id": "invalid_step_expected_decision",
        "kind": "step",
        "initial_state": {"premise": None, "policies": {}, "version": 2},
        "input": "use docker",
        "expected": {
            "decision": {
                "kind": "update",
                "state": {"premise": None, "policies": {"docker": "use"}, "version": 2},
                "unexpected": True,
            },
            "state": {"premise": None, "policies": {"docker": "use"}, "version": 2},
        },
    }

    with pytest.raises(AssertionError, match="invalid keys for expected.decision"):
        _validate_step_fixture(fixture, fixture["id"])


def test_state_json_validator_rejects_unknown_error_field() -> None:
    fixture = {
        "id": "invalid_state_json_error",
        "kind": "state_json",
        "initial_state": {"premise": None, "policies": {}, "version": 2},
        "action": {"fn": "import_json", "payload": "{"},
        "expected": {
            "error": {
                "type": "ValueError",
                "message_contains": "Invalid JSON payload",
                "unexpected": True,
            },
            "state": {"premise": None, "policies": {}, "version": 2},
        },
    }

    with pytest.raises(AssertionError, match="invalid keys for expected.error"):
        _validate_state_json_fixture(fixture, fixture["id"])


def test_conformance_fixture_identity_rejects_filename_id_mismatch() -> None:
    path = Path("/tmp/fixture_name.json")
    fixture_id = "different_fixture_id"

    with pytest.raises(AssertionError, match="filename/id mismatch"):
        _assert_fixture_path_matches_id(path, fixture_id)


def test_state_json_validator_rejects_missing_error_type() -> None:
    fixture = {
        "id": "invalid_state_json_error_missing_type",
        "kind": "state_json",
        "initial_state": {"premise": None, "policies": {}, "version": 2},
        "action": {"fn": "import_json", "payload": "{"},
        "expected": {
            "error": {
                "message_contains": "Invalid JSON payload",
            },
            "state": {"premise": None, "policies": {}, "version": 2},
        },
    }

    with pytest.raises(AssertionError, match="invalid keys for expected.error"):
        _validate_state_json_fixture(fixture, fixture["id"])


def test_state_json_validator_rejects_non_string_error_type() -> None:
    fixture = {
        "id": "invalid_state_json_error_type_shape",
        "kind": "state_json",
        "initial_state": {"premise": None, "policies": {}, "version": 2},
        "action": {"fn": "import_json", "payload": "{"},
        "expected": {
            "error": {
                "type": 123,
                "message_contains": "Invalid JSON payload",
            },
            "state": {"premise": None, "policies": {}, "version": 2},
        },
    }

    with pytest.raises(AssertionError):
        _validate_state_json_fixture(fixture, fixture["id"])


def test_state_json_runner_rejects_incorrect_error_type_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = {
        "id": "invalid_state_json_runtime_error_type",
        "kind": "state_json",
        "initial_state": {"premise": None, "policies": {}, "version": 2},
        "action": {"fn": "import_json", "payload": "{"},
        "expected": {
            "error": {
                "type": "ValueError",
                "message_contains": "boom",
            },
            "state": {"premise": None, "policies": {}, "version": 2},
        },
    }
    engine = create_engine(state=fixture["initial_state"])

    def _boom(_: str) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(engine, "import_json", _boom)

    action = fixture["action"]
    expected = fixture["expected"]
    error = expected["error"]

    with pytest.raises(AssertionError, match=fixture["id"]):
        with pytest.raises(Exception, match=error["message_contains"]) as exc_info:
            engine.import_json(action["payload"])
        assert type(exc_info.value).__name__ == error["type"], fixture["id"]


def test_state_json_validator_rejects_unknown_action_fn() -> None:
    fixture = {
        "id": "invalid_state_json_fn",
        "kind": "state_json",
        "initial_state": {"premise": None, "policies": {}, "version": 2},
        "action": {"fn": "delete_json"},
        "expected": {
            "state": {"premise": None, "policies": {}, "version": 2},
        },
    }

    with pytest.raises(AssertionError):
        _validate_state_json_fixture(fixture, fixture["id"])


def test_state_json_validator_rejects_wrong_branch_action_fields() -> None:
    fixture = {
        "id": "invalid_state_json_export_fields",
        "kind": "state_json",
        "initial_state": {"premise": None, "policies": {}, "version": 2},
        "action": {"fn": "export_json", "payload": "{}"},
        "expected": {
            "payload": "{}",
            "state": {"premise": None, "policies": {}, "version": 2},
        },
    }

    with pytest.raises(AssertionError, match="invalid keys for action"):
        _validate_state_json_fixture(fixture, fixture["id"])


def test_controller_validator_rejects_unknown_preview_result_field() -> None:
    fixture = {
        "id": "invalid_controller_preview_result",
        "kind": "controller",
        "initial_state": {"premise": None, "policies": {}, "version": 2},
        "action": {"fn": "preview", "input": "use docker"},
        "expected": {
            "result": {
                "output_version": 1,
                "mode": "preview",
                "decision": {
                    "kind": "update",
                    "state": {"premise": None, "policies": {"docker": "use"}, "version": 2},
                },
                "state_before": {"premise": None, "policies": {}, "version": 2},
                "state_after": {"premise": None, "policies": {"docker": "use"}, "version": 2},
                "diff": {
                    "changed": True,
                    "premise": {"before": None, "after": None, "changed": False},
                    "policies": {"added": {"docker": "use"}, "removed": {}, "changed": {}},
                },
                "would_mutate": True,
                "unexpected": True,
            },
            "state_after_preview": {"premise": None, "policies": {}, "version": 2},
        },
    }

    with pytest.raises(AssertionError, match="invalid keys for expected.result"):
        _validate_controller_fixture(fixture, fixture["id"])


def test_controller_validator_rejects_unknown_action_fn() -> None:
    fixture = {
        "id": "invalid_controller_fn",
        "kind": "controller",
        "initial_state": {"premise": None, "policies": {}, "version": 2},
        "action": {"fn": "execute", "input": "use docker"},
        "expected": {"state": {"premise": None, "policies": {}, "version": 2}},
    }

    with pytest.raises(AssertionError):
        _validate_controller_fixture(fixture, fixture["id"])


def test_controller_validator_rejects_wrong_branch_action_fields() -> None:
    fixture = {
        "id": "invalid_controller_step_fields",
        "kind": "controller",
        "initial_state": {"premise": None, "policies": {}, "version": 2},
        "action": {
            "fn": "step",
            "input": "use docker",
            "before": {"premise": None, "policies": {}, "version": 2},
        },
        "expected": {
            "result": {
                "output_version": 1,
                "mode": "step",
                "decision": {
                    "kind": "update",
                    "state": {"premise": None, "policies": {"docker": "use"}, "version": 2},
                },
                "state": {"premise": None, "policies": {"docker": "use"}, "version": 2},
            },
            "state": {"premise": None, "policies": {"docker": "use"}, "version": 2},
        },
    }

    with pytest.raises(AssertionError, match="invalid keys for action"):
        _validate_controller_fixture(fixture, fixture["id"])


def test_grammar_validator_rejects_unknown_validated_field() -> None:
    fixture = {
        "id": "invalid_grammar_validated",
        "kind": "grammar",
        "action": {"fn": "validate_directive", "text": "use docker"},
        "expected": {
            "validated": {
                "text": "use docker",
                "kind": "use_item",
                "unexpected": True,
            }
        },
    }

    with pytest.raises(AssertionError, match="invalid keys for expected.validated"):
        _validate_grammar_fixture(fixture, fixture["id"])


def test_grammar_validator_rejects_unknown_action_fn() -> None:
    fixture = {
        "id": "invalid_grammar_fn",
        "kind": "grammar",
        "action": {"fn": "parse_directive", "text": "use docker"},
        "expected": {"validated": None},
    }

    with pytest.raises(AssertionError):
        _validate_grammar_fixture(fixture, fixture["id"])


def test_grammar_validator_rejects_wrong_branch_action_fields() -> None:
    fixture = {
        "id": "invalid_grammar_validate_fields",
        "kind": "grammar",
        "action": {
            "fn": "validate_directive",
            "text": "use docker",
            "kind": "use_item",
        },
        "expected": {"validated": {"text": "use docker", "kind": "use_item"}},
    }

    with pytest.raises(AssertionError, match="invalid keys for action"):
        _validate_grammar_fixture(fixture, fixture["id"])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("identity_assertions", {}),
        ("caller_owned_observations", {}),
    ],
)
def test_mutation_isolation_validator_rejects_non_list_optional_expected_collections(
    field: str, value: object
) -> None:
    fixture = {
        "id": f"invalid_{field}",
        "kind": "mutation_isolation",
        "initial_state": {"premise": None, "policies": {}, "version": 2},
        "operation": {"fn": "engine.state", "result_handle": "state_snapshot"},
        "handles": {"state_snapshot": {"kind": "defensive_snapshot"}},
        "mutations": [
            {
                "target_handle": "state_snapshot",
                "path": ["premise"],
                "op": "set",
                "value": "mutated",
            }
        ],
        "expected": {
            "authoritative_state": {"premise": None, "policies": {}, "version": 2},
            field: value,
        },
    }

    with pytest.raises(AssertionError):
        _validate_mutation_isolation_fixture(fixture, fixture["id"])


@pytest.mark.parametrize("value", [False, "true", 1, None])
def test_mutation_isolation_validator_rejects_invalid_preview_live_state_unchanged_values(
    value: object,
) -> None:
    fixture = {
        "id": "invalid_preview_live_state_unchanged_value",
        "kind": "mutation_isolation",
        "initial_state": {"premise": None, "policies": {}, "version": 2},
        "operation": {
            "fn": "controller.preview",
            "input": "use docker",
            "result_handle": "preview_result",
        },
        "handles": {
            "preview_result": {"kind": "caller_owned_result_envelope"},
            "state_before": {
                "kind": "defensive_snapshot",
                "from_handle": "preview_result",
                "path": ["state_before"],
            },
            "state_after": {
                "kind": "defensive_snapshot",
                "from_handle": "preview_result",
                "path": ["state_after"],
            },
        },
        "mutations": [
            {
                "target_handle": "state_before",
                "path": ["premise"],
                "op": "set",
                "value": "mutated",
            }
        ],
        "expected": {
            "authoritative_state": {"premise": None, "policies": {}, "version": 2},
            "preview_live_state_unchanged": value,
        },
    }

    with pytest.raises(AssertionError):
        _validate_mutation_isolation_fixture(fixture, fixture["id"])


def test_mutation_isolation_validator_rejects_preview_flag_on_non_preview_operation() -> None:
    fixture = {
        "id": "invalid_preview_live_state_unchanged_non_preview",
        "kind": "mutation_isolation",
        "initial_state": {"premise": None, "policies": {}, "version": 2},
        "operation": {"fn": "engine.state", "result_handle": "state_snapshot"},
        "handles": {"state_snapshot": {"kind": "defensive_snapshot"}},
        "mutations": [
            {
                "target_handle": "state_snapshot",
                "path": ["premise"],
                "op": "set",
                "value": "mutated",
            }
        ],
        "expected": {
            "authoritative_state": {"premise": None, "policies": {}, "version": 2},
            "preview_live_state_unchanged": True,
        },
    }

    with pytest.raises(AssertionError):
        _validate_mutation_isolation_fixture(fixture, fixture["id"])


def _execute_mutation_isolation_operation(
    fixture: dict[str, object],
) -> tuple[object, dict[str, object], dict[str, object]]:
    operation = fixture["operation"]
    initial_state = fixture["initial_state"]
    handles: dict[str, object] = {}
    fn = operation["fn"]

    if fn == "create_engine":
        constructor_handle = operation["constructor_state_handle"]
        assert isinstance(constructor_handle, str)
        constructor_state = deepcopy(initial_state)
        handles[constructor_handle] = constructor_state
        engine = create_engine(state=constructor_state)
        return engine, handles, {}

    engine = create_engine(state=initial_state)
    produced: dict[str, object] = {}

    if fn == "engine.state":
        result_handle = operation["result_handle"]
        assert isinstance(result_handle, str)
        handles[result_handle] = engine.state
        return engine, handles, produced

    if fn == "engine.policies":
        result_handle = operation["result_handle"]
        assert isinstance(result_handle, str)
        handles[result_handle] = engine.policies
        return engine, handles, produced

    if fn == "engine.premise":
        result_handle = operation["result_handle"]
        assert isinstance(result_handle, str)
        handles[result_handle] = {"value": engine.premise}
        return engine, handles, produced

    if fn == "engine.step":
        decision = engine.step(operation["input"])
        result_handle = operation["result_handle"]
        assert isinstance(result_handle, str)
        handles[result_handle] = decision
        produced[result_handle] = decision
    elif fn == "controller.step":
        step_result = step(engine, operation["input"])
        result_handle = operation["result_handle"]
        assert isinstance(result_handle, str)
        handles[result_handle] = step_result
        produced[result_handle] = step_result
    elif fn == "controller.preview":
        step_result = preview(engine, operation["input"])
        result_handle = operation["result_handle"]
        assert isinstance(result_handle, str)
        handles[result_handle] = step_result
        produced[result_handle] = step_result
    elif fn == "get_decision_state":
        decision = engine.step(operation["input"])
        source_handle = operation["source_handle"]
        result_handle = operation["result_handle"]
        assert isinstance(source_handle, str)
        assert isinstance(result_handle, str)
        handles[source_handle] = decision
        produced[source_handle] = decision
        handles[result_handle] = get_decision_state(decision)
    else:
        assert fn == "get_step_state"
        step_result = step(engine, operation["input"])
        source_handle = operation["source_handle"]
        result_handle = operation["result_handle"]
        assert isinstance(source_handle, str)
        assert isinstance(result_handle, str)
        handles[source_handle] = step_result
        produced[source_handle] = step_result
        handles[result_handle] = get_step_state(step_result)

    for handle_name, handle_spec in fixture["handles"].items():
        if handle_name in handles:
            continue
        from_handle = handle_spec.get("from_handle")
        if from_handle is None:
            continue
        assert isinstance(from_handle, str)
        handles[handle_name] = _get_path_value(handles[from_handle], handle_spec["path"])

    return engine, handles, produced


def test_mutation_isolation_fixtures() -> None:
    for path in _json_files(_MUTATION_ISOLATION_FIXTURES_DIR):
        fixture = _load(path)
        fixture_id = fixture["id"]
        _validate_mutation_isolation_fixture(fixture, fixture_id)

        engine, handles, _ = _execute_mutation_isolation_operation(fixture)
        expected = fixture["expected"]

        live_state_before_mutation = engine.state

        for mutation in fixture["mutations"]:
            target_handle = mutation["target_handle"]
            assert isinstance(target_handle, str), fixture_id
            _set_path_value(handles[target_handle], mutation["path"], mutation["value"])

        assert engine.state == expected["authoritative_state"], fixture_id

        if expected.get("preview_live_state_unchanged") is True:
            assert engine.state == live_state_before_mutation, fixture_id

        for assertion in expected.get("identity_assertions", []):
            left_handle = assertion["left_handle"]
            right_handle = assertion["right_handle"]
            assert isinstance(left_handle, str), fixture_id
            assert isinstance(right_handle, str), fixture_id
            left_value = handles[left_handle]
            right_value = _get_path_value(handles[right_handle], assertion["right_path"])
            if assertion["same_identity"]:
                assert left_value is right_value, fixture_id
            else:
                assert left_value is not right_value, fixture_id

        for observation in expected.get("caller_owned_observations", []):
            handle = observation["handle"]
            assert isinstance(handle, str), fixture_id
            assert _get_path_value(handles[handle], observation["path"]) == observation["value"], (
                fixture_id
            )
