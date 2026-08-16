import json
from pathlib import Path

import pytest
from _decision_test_helpers import decision_observation

import context_compiler.grammar as grammar_module
from context_compiler import (
    DECISION_ERROR,
    Engine,
)
from context_compiler.grammar import (
    CanonicalDirective,
    decompose_directive,
)

_STEP_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "conformance" / "step"
_STATE_JSON_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "state-json"
)
_GRAMMAR_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "conformance" / "grammar"
_MUTATION_ISOLATION_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "mutation-isolation"
)
_APPLY_DIRECTIVE_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "apply-directive"
)
_CONTROLLER_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "conformance" / "controller"
)


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
    _assert_allowed_keys(
        operation, {"fn", "input", "result_handle"} & set(operation), fixture_id, "operation"
    )
    assert operation["fn"] in {"engine.step", "engine.policies", "engine.premise"}, fixture_id
    if operation["fn"] == "engine.step":
        _assert_allowed_keys(operation, {"fn", "input", "result_handle"}, fixture_id, "operation")
        assert isinstance(operation["input"], str), fixture_id
    else:
        _assert_allowed_keys(operation, {"fn", "result_handle"}, fixture_id, "operation")
    assert isinstance(operation["result_handle"], str), fixture_id

    handles = fixture["handles"]
    assert isinstance(handles, dict), fixture_id
    assert operation["result_handle"] in handles, fixture_id
    for handle_name, handle_meta in handles.items():
        assert isinstance(handle_name, str), fixture_id
        assert isinstance(handle_meta, dict), fixture_id
        _assert_allowed_keys(handle_meta, {"kind"}, fixture_id, f"handles.{handle_name}")
        assert isinstance(handle_meta["kind"], str), fixture_id

    mutations = fixture["mutations"]
    assert isinstance(mutations, list), fixture_id
    for index, mutation in enumerate(mutations):
        assert isinstance(mutation, dict), fixture_id
        _assert_allowed_keys(
            mutation,
            {"target_handle", "path", "op", "value"},
            fixture_id,
            f"mutations[{index}]",
        )
        assert mutation["target_handle"] in handles, fixture_id
        _assert_str_list(mutation["path"], fixture_id, f"mutations[{index}].path")
        assert mutation["op"] == "set", fixture_id

    expected = fixture["expected"]
    assert isinstance(expected, dict), fixture_id
    _assert_allowed_keys(
        expected,
        {"authoritative_state"} | ({"caller_owned_observations"} & set(expected)),
        fixture_id,
        "expected",
    )
    assert isinstance(expected["authoritative_state"], dict), fixture_id
    if "caller_owned_observations" in expected:
        assert isinstance(expected["caller_owned_observations"], dict), fixture_id


def _validate_public_decision(decision: dict[str, object], fixture_id: object, label: str) -> None:
    _assert_allowed_keys(
        decision,
        {"kind", "message"} | ({"failure", "directive", "repairs"} & set(decision)),
        fixture_id,
        label,
    )
    kind = decision.get("kind")
    assert isinstance(kind, str), fixture_id

    if kind in {"no_directive", "update"}:
        assert decision["message"] is None, fixture_id
        return

    assert kind == "error", fixture_id
    assert isinstance(decision["message"], str), fixture_id
    if "failure" in decision:
        assert isinstance(decision["failure"], str), fixture_id
        directive = decision.get("directive")
        assert isinstance(directive, dict), fixture_id
        _assert_allowed_keys(
            directive,
            {"kind", "text", "operands"},
            fixture_id,
            f"{label}.directive",
        )
        assert isinstance(directive["kind"], str), fixture_id
        assert isinstance(directive["text"], str), fixture_id
        assert isinstance(directive["operands"], dict), fixture_id
        repairs = decision.get("repairs")
        assert isinstance(repairs, list), fixture_id
        for index, repair in enumerate(repairs):
            assert isinstance(repair, dict), fixture_id
            _assert_allowed_keys(
                repair,
                {"kind", "text", "operands"},
                fixture_id,
                f"{label}.repairs[{index}]",
            )
            assert isinstance(repair["kind"], str), fixture_id
            assert isinstance(repair["text"], str), fixture_id
            assert isinstance(repair["operands"], dict), fixture_id


def _assert_decision_observation(
    observed: dict[str, object], expected: dict[str, object], fixture_id: object
) -> None:
    if expected["kind"] == DECISION_ERROR:
        assert observed["kind"] == expected["kind"], fixture_id
        for field, value in expected.items():
            assert observed[field] == value, fixture_id
    else:
        assert observed == expected, fixture_id


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


def _validate_apply_directive_fixture(fixture: dict[str, object], fixture_id: object) -> None:
    _assert_allowed_keys(
        fixture,
        {"id", "kind", "initial_state", "action", "expected"} | ({"prelude"} & set(fixture)),
        fixture_id,
        "fixture",
    )
    assert fixture["kind"] == "apply_directive", fixture_id
    assert isinstance(fixture["initial_state"], dict), fixture_id
    if "prelude" in fixture:
        _assert_str_list(fixture["prelude"], fixture_id, "prelude")

    action = fixture["action"]
    assert isinstance(action, dict), fixture_id
    _assert_allowed_keys(action, {"fn", "text"}, fixture_id, "action")
    assert action["fn"] == "apply_directive", fixture_id
    assert isinstance(action["text"], str), fixture_id

    expected = fixture["expected"]
    assert isinstance(expected, dict), fixture_id
    _assert_allowed_keys(expected, {"decision", "state"}, fixture_id, "expected")
    assert isinstance(expected["state"], dict), fixture_id

    decision = expected["decision"]
    assert isinstance(decision, dict), fixture_id
    _validate_public_decision(decision, fixture_id, "expected.decision")


def _validate_grammar_fixture(fixture: dict[str, object], fixture_id: object) -> None:
    _assert_allowed_keys(fixture, {"id", "kind", "action", "expected"}, fixture_id, "fixture")
    assert fixture["kind"] == "grammar", fixture_id

    action = fixture["action"]
    assert isinstance(action, dict), fixture_id
    expected = fixture["expected"]
    assert isinstance(expected, dict), fixture_id
    fn = action["fn"]
    assert fn in {"decompose_directive", "render_directive"}, fixture_id

    if fn == "decompose_directive":
        _assert_allowed_keys(action, {"fn", "text"}, fixture_id, "action")
        assert isinstance(action["text"], str), fixture_id
        _assert_allowed_keys(expected, {"directive"}, fixture_id, "expected")
    else:
        _assert_allowed_keys(action, {"fn", "kind", "operands"}, fixture_id, "action")
        assert isinstance(action["kind"], str), fixture_id
        assert isinstance(action["operands"], dict), fixture_id
        if "error" in expected:
            _assert_allowed_keys(expected, {"error"}, fixture_id, "expected")
            error = expected["error"]
            assert isinstance(error, dict), fixture_id
            _assert_allowed_keys(error, {"type", "message_contains"}, fixture_id, "expected.error")
            assert isinstance(error["type"], str), fixture_id
            assert isinstance(error["message_contains"], str), fixture_id
        else:
            _assert_allowed_keys(expected, {"text", "directive_kind"}, fixture_id, "expected")


def _validate_controller_fixture(fixture: dict[str, object], fixture_id: object) -> None:
    _assert_allowed_keys(
        fixture,
        {"id", "kind", "initial_state", "operations", "expected"},
        fixture_id,
        "fixture",
    )
    assert fixture["kind"] == "controller", fixture_id
    assert isinstance(fixture["initial_state"], dict), fixture_id

    operations = fixture["operations"]
    assert isinstance(operations, list), fixture_id
    for index, operation in enumerate(operations):
        assert isinstance(operation, dict), fixture_id
        fn = operation.get("fn")
        assert isinstance(fn, str), fixture_id

        if fn == "step":
            _assert_allowed_keys(
                operation,
                {"fn", "input", "label"},
                fixture_id,
                f"operations[{index}]",
            )
            assert isinstance(operation["input"], str), fixture_id
            assert isinstance(operation["label"], str), fixture_id
        elif fn == "apply_directive":
            _assert_allowed_keys(
                operation,
                {"fn", "text", "label"},
                fixture_id,
                f"operations[{index}]",
            )
            assert isinstance(operation["text"], str), fixture_id
            assert isinstance(operation["label"], str), fixture_id
        elif fn == "export_json":
            _assert_allowed_keys(operation, {"fn", "label"}, fixture_id, f"operations[{index}]")
            assert isinstance(operation["label"], str), fixture_id
        else:
            assert fn == "import_json", fixture_id
            _assert_allowed_keys(
                operation,
                {"fn"} | ({"payload"} & set(operation)) | ({"payload_ref"} & set(operation)),
                fixture_id,
                f"operations[{index}]",
            )
            has_payload = "payload" in operation
            has_payload_ref = "payload_ref" in operation
            assert has_payload != has_payload_ref, fixture_id
            if has_payload:
                assert isinstance(operation["payload"], str), fixture_id
            if has_payload_ref:
                assert isinstance(operation["payload_ref"], str), fixture_id

    expected = fixture["expected"]
    assert isinstance(expected, dict), fixture_id
    _assert_allowed_keys(expected, {"observations", "equal", "state"}, fixture_id, "expected")
    assert isinstance(expected["observations"], dict), fixture_id
    assert isinstance(expected["equal"], list), fixture_id
    assert isinstance(expected["state"], dict), fixture_id

    for label, observation in expected["observations"].items():
        assert isinstance(label, str), fixture_id
        if isinstance(observation, dict):
            _validate_public_decision(observation, fixture_id, f"expected.observations.{label}")
        else:
            assert isinstance(observation, str), fixture_id

    for index, pair in enumerate(expected["equal"]):
        assert isinstance(pair, list), fixture_id
        assert len(pair) == 2, fixture_id
        assert all(isinstance(item, str) for item in pair), (
            f"{fixture_id}: invalid expected.equal[{index}]"
        )


def _apply_prelude(engine: object, prelude: object) -> None:
    assert isinstance(prelude, list)
    for prior_input in prelude:
        assert isinstance(prior_input, str)
        engine.step(prior_input)


def _state_observation(engine: object) -> dict[str, object]:
    return {
        "premise": engine.premise,
        "policies": dict(engine.policies),
        "version": 2,
    }


def _resolve_handle_path(root: object, path: list[str]) -> object:
    current = root
    for key in path:
        assert isinstance(current, dict)
        current = current[key]
    return current


def _apply_handle_mutation(root: object, path: list[str], value: object) -> None:
    assert path
    current = root
    for key in path[:-1]:
        assert isinstance(current, dict)
        current = current[key]
    assert isinstance(current, dict)
    current[path[-1]] = value


def test_step_fixtures() -> None:
    for path in _json_files(_STEP_FIXTURES_DIR):
        fixture = _load(path)
        fixture_id = fixture["id"]

        _assert_fixture_path_matches_id(path, fixture_id)
        _validate_step_fixture(fixture, fixture_id)

        engine = Engine()
        engine.import_json(
            json.dumps(fixture["initial_state"], sort_keys=True, separators=(",", ":"))
        )
        _apply_prelude(engine, fixture.get("prelude", []))
        decision = engine.step(fixture["input"])

        expected = fixture["expected"]
        expected_decision = expected["decision"]
        observed_decision = decision_observation(decision)
        _assert_decision_observation(observed_decision, expected_decision, fixture_id)

        assert _state_observation(engine) == expected["state"], fixture_id


def test_state_json_fixtures() -> None:
    for path in _json_files(_STATE_JSON_FIXTURES_DIR):
        fixture = _load(path)
        fixture_id = fixture["id"]

        _assert_fixture_path_matches_id(path, fixture_id)
        _validate_state_json_fixture(fixture, fixture_id)
        engine = Engine()
        engine.import_json(
            json.dumps(fixture["initial_state"], sort_keys=True, separators=(",", ":"))
        )
        _apply_prelude(engine, fixture.get("prelude", []))

        action = fixture["action"]
        expected = fixture["expected"]
        fn = action["fn"]

        if fn == "export_json":
            payload = engine.export_json()
            assert payload == expected["payload"], fixture_id
        else:
            payload = action["payload"]
            error = expected.get("error")
            if error is None:
                engine.import_json(payload)
            else:
                with pytest.raises(Exception, match=error["message_contains"]) as exc_info:
                    engine.import_json(payload)
                assert type(exc_info.value).__name__ == error["type"], fixture_id

        assert _state_observation(engine) == expected["state"], fixture_id


def test_apply_directive_fixtures() -> None:
    for path in _json_files(_APPLY_DIRECTIVE_FIXTURES_DIR):
        fixture = _load(path)
        fixture_id = fixture["id"]

        _assert_fixture_path_matches_id(path, fixture_id)
        _validate_apply_directive_fixture(fixture, fixture_id)

        engine = Engine()
        engine.import_json(
            json.dumps(fixture["initial_state"], sort_keys=True, separators=(",", ":"))
        )
        _apply_prelude(engine, fixture.get("prelude", []))

        action = fixture["action"]
        directive = decompose_directive(action["text"])
        assert isinstance(directive, CanonicalDirective), fixture_id
        decision = engine.apply_directive(directive)

        expected = fixture["expected"]
        expected_decision = expected["decision"]
        observed_decision = decision_observation(decision)
        _assert_decision_observation(observed_decision, expected_decision, fixture_id)

        assert _state_observation(engine) == expected["state"], fixture_id


def test_grammar_fixtures() -> None:
    for path in _json_files(_GRAMMAR_FIXTURES_DIR):
        fixture = _load(path)
        fixture_id = fixture["id"]

        _assert_fixture_path_matches_id(path, fixture_id)
        _validate_grammar_fixture(fixture, fixture_id)
        action = fixture["action"]
        expected = fixture["expected"]
        fn = action["fn"]

        if fn == "decompose_directive":
            directive = decompose_directive(action["text"])
            expected_directive = expected["directive"]
            if expected_directive is None:
                assert directive is None, fixture_id
            elif expected_directive.get("kind") == "invalid_directive_syntax":
                assert isinstance(directive, grammar_module.InvalidDirectiveSyntax), fixture_id
                assert directive.failure.value == expected_directive["failure"], fixture_id
                expected_kind = expected_directive.get("directive_kind")
                assert (
                    None if directive.directive_kind is None else directive.directive_kind.value
                ) == expected_kind, fixture_id
                assert directive.missing_operand == expected_directive.get("missing_operand"), (
                    fixture_id
                )
            else:
                assert isinstance(directive, CanonicalDirective), fixture_id
                assert directive.text == expected_directive["text"], fixture_id
                assert directive.kind.value == expected_directive["kind"], fixture_id
                assert dict(directive.operands) == expected_directive["operands"], fixture_id
                assert directive.text == grammar_module._render_directive(
                    directive.kind,
                    **dict(directive.operands),
                ), fixture_id
        else:
            error = expected.get("error")
            if error is not None:
                with pytest.raises(Exception, match=error["message_contains"]) as exc_info:
                    grammar_module._render_directive(action["kind"], **action["operands"])
                assert type(exc_info.value).__name__ == error["type"], fixture_id
            else:
                rendered = grammar_module._render_directive(action["kind"], **action["operands"])
                assert rendered == expected["text"], fixture_id
                directive = decompose_directive(rendered)
                assert isinstance(directive, CanonicalDirective), fixture_id
                assert directive.kind.value == expected["directive_kind"], fixture_id
                assert directive.text == rendered, fixture_id


def test_mutation_isolation_fixtures() -> None:
    for path in _json_files(_MUTATION_ISOLATION_FIXTURES_DIR):
        fixture = _load(path)
        fixture_id = fixture["id"]
        _validate_mutation_isolation_fixture(fixture, fixture_id)
        operation = fixture["operation"]
        fn = operation["fn"]
        engine = Engine()
        engine.import_json(
            json.dumps(fixture["initial_state"], sort_keys=True, separators=(",", ":"))
        )

        handles: dict[str, object]
        if fn == "engine.step":
            handles = {operation["result_handle"]: engine.step(operation["input"])}
        elif fn == "engine.policies":
            handles = {operation["result_handle"]: engine.policies}
        else:
            assert fn == "engine.premise", fixture_id
            handles = {operation["result_handle"]: {"value": engine.premise}}

        for mutation in fixture["mutations"]:
            target = handles[mutation["target_handle"]]
            path = mutation["path"]
            assert isinstance(path, list), fixture_id
            if fn == "engine.step":
                with pytest.raises((AssertionError, AttributeError, TypeError)):
                    _apply_handle_mutation(target, path, mutation["value"])
            else:
                _apply_handle_mutation(target, path, mutation["value"])

        expected = fixture["expected"]
        assert _state_observation(engine) == expected["authoritative_state"], fixture_id

        observations = expected.get("caller_owned_observations")
        if observations is None:
            continue

        assert isinstance(observations, dict), fixture_id
        for label, observation in observations.items():
            assert isinstance(observation, dict), fixture_id
            _assert_allowed_keys(observation, {"target_handle", "path", "value"}, fixture_id, label)
            target = handles[observation["target_handle"]]
            observed = _resolve_handle_path(target, observation["path"])
            assert observed == observation["value"], fixture_id


def test_controller_fixtures() -> None:
    for path in _json_files(_CONTROLLER_FIXTURES_DIR):
        fixture = _load(path)
        fixture_id = fixture["id"]

        _assert_fixture_path_matches_id(path, fixture_id)
        _validate_controller_fixture(fixture, fixture_id)

        engine = Engine()
        engine.import_json(
            json.dumps(fixture["initial_state"], sort_keys=True, separators=(",", ":"))
        )

        observations: dict[str, object] = {}
        for operation in fixture["operations"]:
            fn = operation["fn"]

            if fn == "step":
                observations[operation["label"]] = decision_observation(
                    engine.step(operation["input"])
                )
                continue

            if fn == "apply_directive":
                directive = decompose_directive(operation["text"])
                assert isinstance(directive, CanonicalDirective), fixture_id
                observations[operation["label"]] = decision_observation(
                    engine.apply_directive(directive)
                )
                continue

            if fn == "export_json":
                observations[operation["label"]] = engine.export_json()
                continue

            assert fn == "import_json", fixture_id
            payload = operation.get("payload")
            if payload is None:
                payload_ref = operation["payload_ref"]
                payload = observations[payload_ref]
                assert isinstance(payload, str), fixture_id
            engine.import_json(payload)

        expected = fixture["expected"]
        for label, expected_observation in expected["observations"].items():
            if isinstance(expected_observation, dict) and "kind" in expected_observation:
                _assert_decision_observation(observations[label], expected_observation, fixture_id)
            else:
                assert observations[label] == expected_observation, fixture_id

        for left, right in expected["equal"]:
            assert observations[left] == observations[right], fixture_id

        assert _state_observation(engine) == expected["state"], fixture_id
