import json
from pathlib import Path

import pytest

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


def _validate_public_decision(decision: dict[str, object], fixture_id: object, label: str) -> None:
    _assert_allowed_keys(decision, {"kind", "message"}, fixture_id, label)
    kind = decision.get("kind")
    assert isinstance(kind, str), fixture_id

    if kind in {"no_directive", "update"}:
        assert decision["message"] is None, fixture_id
        return

    assert kind == "error", fixture_id
    assert isinstance(decision["message"], str), fixture_id


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
        _assert_allowed_keys(expected, {"text", "directive_kind"}, fixture_id, "expected")


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
        operation = fixture["operation"]
        fn = operation["fn"]
        engine = Engine()
        engine.import_json(
            json.dumps(fixture["initial_state"], sort_keys=True, separators=(",", ":"))
        )

        if fn == "engine.step":
            decision = engine.step(operation["input"])
            decision["message"] = "mutated note"
            assert _state_observation(engine) == fixture["expected"]["authoritative_state"], (
                fixture_id
            )
            continue

        if fn == "engine.policies":
            policies = engine.policies
            policies["docker"] = "prohibit"
            assert _state_observation(engine) == fixture["expected"]["authoritative_state"], (
                fixture_id
            )
            continue

        assert fn == "engine.premise", fixture_id
        premise_box = {"value": engine.premise}
        premise_box["value"] = "mutated premise"
        assert _state_observation(engine) == fixture["expected"]["authoritative_state"], fixture_id
