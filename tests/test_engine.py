import json
from collections.abc import Mapping
from types import MappingProxyType

import pytest

from context_compiler import (
    DECISION_ERROR,
    DECISION_NO_DIRECTIVE,
    DECISION_UPDATE,
    Engine,
)
from context_compiler.engine import (
    _load_state_obj,
)
from context_compiler.grammar import (
    CanonicalDirective,
    DirectiveKind,
    decompose_directive,
)

pytestmark = pytest.mark.contract


def _observations(engine: object) -> tuple[str | None, dict[str, str]]:
    return engine.premise, dict(engine.policies)


def _assert_observations(
    engine: object,
    *,
    premise: str | None,
    policies: dict[str, str],
) -> None:
    assert engine.premise == premise
    assert dict(engine.policies) == policies


def _import_state(engine: object, payload: dict[str, object]) -> None:
    engine.import_json(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _canonical_directive(
    text: str,
    kind: DirectiveKind,
    **operands: str,
) -> CanonicalDirective:
    return CanonicalDirective(text=text, kind=kind, operands=MappingProxyType(operands))


@pytest.mark.parametrize(
    ("directive", "initial_state", "expected_decision", "expected_state"),
    [
        (
            _canonical_directive(
                "set premise concise replies",
                DirectiveKind.SET_PREMISE,
                value="concise replies",
            ),
            None,
            {"kind": DECISION_UPDATE, "message": None},
            (("concise replies"), {}),
        ),
        (
            _canonical_directive(
                "change premise to concise replies",
                DirectiveKind.CHANGE_PREMISE,
                value="concise replies",
            ),
            {"premise": "verbose replies", "policies": {}, "version": 2},
            {"kind": DECISION_UPDATE, "message": None},
            (("concise replies"), {}),
        ),
        (
            _canonical_directive("use docker", DirectiveKind.USE_ITEM, item="docker"),
            None,
            {"kind": DECISION_UPDATE, "message": None},
            (None, {"docker": "use"}),
        ),
        (
            _canonical_directive("prohibit peanuts", DirectiveKind.PROHIBIT_ITEM, item="peanuts"),
            None,
            {"kind": DECISION_UPDATE, "message": None},
            (None, {"peanuts": "prohibit"}),
        ),
        (
            _canonical_directive(
                "remove policy docker",
                DirectiveKind.REMOVE_POLICY,
                item="docker",
            ),
            {"premise": None, "policies": {"docker": "use"}, "version": 2},
            {"kind": DECISION_UPDATE, "message": None},
            (None, {}),
        ),
        (
            _canonical_directive(
                "use podman instead of docker",
                DirectiveKind.REPLACE_USE,
                new_item="podman",
                old_item="docker",
            ),
            {"premise": None, "policies": {"docker": "use"}, "version": 2},
            {"kind": DECISION_UPDATE, "message": None},
            (None, {"podman": "use"}),
        ),
        (
            _canonical_directive("clear premise", DirectiveKind.CLEAR_PREMISE),
            {"premise": "concise replies", "policies": {"docker": "use"}, "version": 2},
            {"kind": DECISION_UPDATE, "message": None},
            (None, {"docker": "use"}),
        ),
        (
            _canonical_directive("reset policies", DirectiveKind.RESET_POLICIES),
            {"premise": "concise replies", "policies": {"docker": "use"}, "version": 2},
            {"kind": DECISION_UPDATE, "message": None},
            ("concise replies", {}),
        ),
        (
            _canonical_directive("clear state", DirectiveKind.CLEAR_STATE),
            {"premise": "concise replies", "policies": {"docker": "use"}, "version": 2},
            {"kind": DECISION_UPDATE, "message": None},
            (None, {}),
        ),
    ],
)
def test_apply_directive_accepts_all_canonical_directive_kinds(
    directive: CanonicalDirective,
    initial_state: dict[str, object] | None,
    expected_decision: dict[str, str | None],
    expected_state: tuple[str | None, dict[str, str]],
) -> None:
    engine = Engine()
    if initial_state is not None:
        _import_state(engine, initial_state)

    decision = engine.apply_directive(directive)

    assert decision == expected_decision
    _assert_observations(engine, premise=expected_state[0], policies=expected_state[1])


@pytest.mark.parametrize(
    ("directive", "initial_state", "expected_decision", "expected_state"),
    [
        (
            _canonical_directive(
                "set premise concise replies",
                DirectiveKind.SET_PREMISE,
                value="concise replies",
            ),
            {"premise": "existing premise", "policies": {}, "version": 2},
            {
                "kind": DECISION_ERROR,
                "message": "Premise already set.\nUse 'change premise to <value>' to modify it.",
            },
            ("existing premise", {}),
        ),
        (
            _canonical_directive(
                "change premise to concise replies",
                DirectiveKind.CHANGE_PREMISE,
                value="concise replies",
            ),
            None,
            {
                "kind": DECISION_ERROR,
                "message": "No premise is set.\nUse 'set premise <value>' to define one.",
            },
            (None, {}),
        ),
        (
            _canonical_directive("use docker", DirectiveKind.USE_ITEM, item="docker"),
            {"premise": None, "policies": {"docker": "prohibit"}, "version": 2},
            {
                "kind": DECISION_ERROR,
                "message": (
                    '"docker" is currently prohibited.\nRemove or replace it before using it.'
                ),
            },
            (None, {"docker": "prohibit"}),
        ),
        (
            _canonical_directive("prohibit docker", DirectiveKind.PROHIBIT_ITEM, item="docker"),
            {"premise": None, "policies": {"docker": "use"}, "version": 2},
            {
                "kind": DECISION_ERROR,
                "message": (
                    '"docker" is currently in use.\nRemove or replace it before prohibiting it.'
                ),
            },
            (None, {"docker": "use"}),
        ),
        (
            _canonical_directive(
                "use docker instead of kubectl",
                DirectiveKind.REPLACE_USE,
                new_item="docker",
                old_item="kubectl",
            ),
            {"premise": None, "policies": {"docker": "prohibit"}, "version": 2},
            {
                "kind": DECISION_ERROR,
                "message": (
                    '"docker" is currently prohibited.\n'
                    "Submit explicit directive(s) to remove it or use a different item."
                ),
            },
            (None, {"docker": "prohibit"}),
        ),
    ],
)
def test_apply_directive_preserves_state_for_semantic_errors(
    directive: CanonicalDirective,
    initial_state: dict[str, object] | None,
    expected_decision: dict[str, str | None],
    expected_state: tuple[str | None, dict[str, str]],
) -> None:
    engine = Engine()
    if initial_state is not None:
        _import_state(engine, initial_state)

    decision = engine.apply_directive(directive)

    assert decision == expected_decision
    _assert_observations(engine, premise=expected_state[0], policies=expected_state[1])


def test_apply_directive_updates_state_from_canonical_directive() -> None:
    engine = Engine()
    parsed = decompose_directive("use docker")

    assert isinstance(parsed, CanonicalDirective)
    decision = engine.apply_directive(parsed)

    assert decision == {"kind": DECISION_UPDATE, "message": None}
    _assert_observations(engine, premise=None, policies={"docker": "use"})


def test_step_routes_canonical_directives_through_apply_directive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = Engine()
    parsed = decompose_directive("use docker")
    assert isinstance(parsed, CanonicalDirective)

    seen: list[CanonicalDirective] = []
    original = engine.apply_directive

    def recording_apply_directive(directive: CanonicalDirective) -> dict[str, str | None]:
        seen.append(directive)
        return original(directive)

    monkeypatch.setattr(engine, "apply_directive", recording_apply_directive)

    decision = engine.step("use docker")

    assert decision == {"kind": DECISION_UPDATE, "message": None}
    assert seen == [parsed]


def test_decompose_directive_rejects_invalid_and_nondirective_inputs() -> None:
    assert not isinstance(decompose_directive("set premise"), CanonicalDirective)
    assert not isinstance(decompose_directive("change premise to"), CanonicalDirective)
    assert not isinstance(decompose_directive("use"), CanonicalDirective)
    assert not isinstance(decompose_directive("prohibit"), CanonicalDirective)
    assert not isinstance(decompose_directive("remove policy"), CanonicalDirective)
    assert not isinstance(decompose_directive("use instead of docker"), CanonicalDirective)
    assert not isinstance(
        decompose_directive("use docker and prohibit peanuts"), CanonicalDirective
    )
    assert not isinstance(decompose_directive("hello there"), CanonicalDirective)


def test_pre_mutation_error_empty_operand_branches_remain_stable() -> None:
    engine = Engine()
    set_premise = CanonicalDirective(
        text="set premise ",
        kind=DirectiveKind.SET_PREMISE,
        operands=MappingProxyType({"value": ""}),
    )
    change_premise = CanonicalDirective(
        text="change premise to ",
        kind=DirectiveKind.CHANGE_PREMISE,
        operands=MappingProxyType({"value": ""}),
    )
    remove_policy = CanonicalDirective(
        text="remove policy ",
        kind=DirectiveKind.REMOVE_POLICY,
        operands=MappingProxyType({"item": ""}),
    )
    use_item = CanonicalDirective(
        text="use ",
        kind=DirectiveKind.USE_ITEM,
        operands=MappingProxyType({"item": ""}),
    )
    prohibit_item = CanonicalDirective(
        text="prohibit ",
        kind=DirectiveKind.PROHIBIT_ITEM,
        operands=MappingProxyType({"item": ""}),
    )

    assert engine._pre_mutation_error(set_premise) == {  # noqa: SLF001
        "kind": "error",
        "message": (
            "Premise value cannot be empty.\nUse 'set premise <value>' with a non-empty value."
        ),
    }
    assert engine._pre_mutation_error(change_premise) == {  # noqa: SLF001
        "kind": "error",
        "message": (
            "Premise value cannot be empty.\n"
            "Use 'change premise to <value>' with a non-empty value."
        ),
    }
    assert engine._pre_mutation_error(remove_policy) == {  # noqa: SLF001
        "kind": "error",
        "message": (
            "Policy item cannot be empty.\nUse 'remove policy <item>' with a non-empty value."
        ),
    }
    assert engine._pre_mutation_error(use_item) == {  # noqa: SLF001
        "kind": "error",
        "message": "Policy item cannot be empty.\nUse 'use <item>' with a non-empty value.",
    }
    assert engine._pre_mutation_error(prohibit_item) == {  # noqa: SLF001
        "kind": "error",
        "message": ("Policy item cannot be empty.\nUse 'prohibit <item>' with a non-empty value."),
    }


def test_initial_state_and_engine_properties() -> None:
    engine = Engine()
    _assert_observations(engine, premise=None, policies={})


def test_policies_property_returns_mapping_snapshot() -> None:
    engine = Engine()
    assert isinstance(engine.policies, Mapping)
    assert engine.policies == {}


def test_premise_property_exposes_authoritative_premise_value() -> None:
    engine = Engine()
    assert engine.premise is None

    engine.step("set premise concise replies")

    assert engine.premise == "concise replies"


def test_policies_property_returns_defensive_copy() -> None:
    engine = Engine()
    engine.step("use docker")

    policies = engine.policies
    assert isinstance(policies, Mapping)
    policies["docker"] = "prohibit"

    _assert_observations(engine, premise=None, policies={"docker": "use"})


def test_export_json_returns_complete_representation_of_state() -> None:
    engine = Engine()
    payload = engine.export_json()
    assert json.loads(payload) == {"premise": None, "policies": {}, "version": 2}


def test_export_json_is_canonical_sorted_and_compact() -> None:
    engine = Engine()
    engine.step("use zeta")
    engine.step("use alpha")
    payload = engine.export_json()

    assert payload == '{"policies":{"alpha":"use","zeta":"use"},"premise":null,"version":2}'


def test_import_json_restores_state_exactly() -> None:
    engine = Engine()
    expected = {
        "premise": "Use concise output",
        "policies": {"docker": "prohibit", "pytest": "use"},
        "version": 2,
    }

    engine.import_json(json.dumps(expected))

    _assert_observations(
        engine,
        premise="Use concise output",
        policies={"docker": "prohibit", "pytest": "use"},
    )


def test_export_import_round_trip_preserves_state() -> None:
    source = Engine()
    _import_state(
        source,
        {
            "premise": "Use concise output",
            "policies": {"docker": "prohibit", "pytest": "use"},
            "version": 2,
        },
    )

    target = Engine()
    target.import_json(source.export_json())

    assert _observations(target) == _observations(source)


def test_import_json_invalid_json_and_unsupported_version_are_rejected() -> None:
    engine = Engine()

    with pytest.raises(ValueError, match="Invalid JSON payload"):
        engine.import_json("{")

    with pytest.raises(ValueError, match="Unsupported state version"):
        engine.import_json(
            json.dumps(
                {
                    "premise": None,
                    "policies": {},
                    "version": 1,
                }
            )
        )


def test_import_json_rejects_non_object_payload() -> None:
    engine = Engine()
    with pytest.raises(ValueError, match="Invalid state payload"):
        engine.import_json('["not", "an", "object"]')


def test_internal_state_loader_rejects_non_string_policy_keys() -> None:
    payload = {
        "premise": None,
        "policies": {1: "use"},
        "version": 2,
    }

    with pytest.raises(ValueError, match="Invalid state payload"):
        _load_state_obj(payload)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "policies",
    [
        {" ": "use"},
        {"\t": "use"},
        {" \t ": "use"},
    ],
)
def test_import_json_rejects_policy_keys_that_normalize_to_empty(
    policies: dict[str, str],
) -> None:
    engine = Engine()
    with pytest.raises(ValueError, match="Invalid state payload"):
        engine.import_json(
            json.dumps(
                {
                    "premise": None,
                    "policies": policies,
                    "version": 2,
                }
            )
        )


def test_import_json_rejects_empty_normalized_key_atomically() -> None:
    engine = Engine()
    engine.step("use kubectl")
    before = _observations(engine)

    with pytest.raises(ValueError, match="Invalid state payload"):
        engine.import_json(
            json.dumps(
                {
                    "premise": None,
                    "policies": {"Docker": "use", " ": "use"},
                    "version": 2,
                }
            )
        )

    assert _observations(engine) == before


def test_import_json_accepts_valid_policy_key_and_normalizes_it() -> None:
    engine = Engine()

    engine.import_json(
        json.dumps(
            {
                "premise": None,
                "policies": {"Docker": "use"},
                "version": 2,
            }
        )
    )

    _assert_observations(engine, premise=None, policies={"docker": "use"})


def test_replace_use_clarifies_when_old_policy_is_not_use_in_invalid_internal_state() -> None:
    engine = Engine()
    # Defensive-path coverage for impossible external state values.
    engine._state["policies"]["docker"] = "invalid"  # type: ignore[assignment]  # noqa: SLF001

    decision = engine.step("use kubectl instead of docker")

    assert decision == {
        "kind": "error",
        "message": (
            "\"docker\" is not currently in use.\nReplacement requires an active 'use' policy."
        ),
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"premise": None, "version": 2},
        {"premise": [], "policies": {}, "version": 2},
        {"premise": None, "policies": [], "version": 2},
        {"premise": None, "policies": {"docker": "deny"}, "version": 2},
    ],
)
def test_import_json_rejects_structurally_invalid_payload(payload: dict[str, object]) -> None:
    engine = Engine()
    with pytest.raises(ValueError):
        engine.import_json(json.dumps(payload))


def test_import_json_normalizes_policy_keys() -> None:
    engine = Engine()
    engine.import_json(
        json.dumps(
            {
                "premise": None,
                "policies": {
                    " The Docker ": "prohibit",
                    "dont use": "use",
                },
                "version": 2,
            }
        )
    )

    _assert_observations(
        engine,
        premise=None,
        policies={"dont use": "use", "the docker": "prohibit"},
    )


def test_import_json_sanitizes_premise_value() -> None:
    engine = Engine()
    engine.import_json(
        json.dumps(
            {
                "premise": "  Use   concise’  output  ",
                "policies": {},
                "version": 2,
            }
        )
    )

    assert engine.premise == "Use concise' output"


def test_import_json_canonicalizes_policies_by_normalized_key() -> None:
    engine = Engine()
    engine.import_json(
        json.dumps(
            {
                "premise": None,
                "policies": {
                    "  The Docker ": "prohibit",
                    "docker": "use",
                },
                "version": 2,
            }
        )
    )

    assert dict(engine.policies) == {"docker": "use", "the docker": "prohibit"}


def test_non_matching_input_is_no_directive() -> None:
    engine = Engine()
    before = _observations(engine)

    for text in [
        "hello there",
        "please use docker",
        "allow docker",
        "I am using x",
        "set X",
        "no use docker",
        "don't use docker",
    ]:
        decision = engine.step(text)
        assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}

    assert _observations(engine) == before


def test_lexical_normalization_accepts_canonical_directives() -> None:
    engine = Engine()

    assert engine.step("clear premise ")["kind"] == DECISION_UPDATE
    assert engine.step(" reset policies")["kind"] == DECISION_UPDATE
    assert engine.step("clear state\t")["kind"] == DECISION_UPDATE
    assert engine.step("Use docker")["kind"] == DECISION_UPDATE
    assert engine.step("use\tdocker")["kind"] == DECISION_UPDATE
    assert engine.step(" prohibit docker")["kind"] == DECISION_ERROR


def test_clear_premise_is_idempotent_update_when_already_null() -> None:
    engine = Engine()
    before = _observations(engine)

    decision = engine.step("clear premise")
    assert decision == {"kind": DECISION_UPDATE, "message": None}
    assert _observations(engine) == before


def test_clear_state_is_idempotent_update_when_already_empty() -> None:
    engine = Engine()
    before = _observations(engine)

    decision = engine.step("clear state")
    assert decision == {"kind": DECISION_UPDATE, "message": None}
    assert _observations(engine) == before


def test_set_premise_lifecycle_rules() -> None:
    engine = Engine()

    d1 = engine.step("set premise   concise   replies")
    assert d1["kind"] == DECISION_UPDATE
    assert engine.premise == "concise replies"

    before = _observations(engine)
    d2 = engine.step("set premise new")
    assert d2 == {
        "kind": DECISION_ERROR,
        "message": ("Premise already set.\nUse 'change premise to <value>' to modify it."),
    }
    assert _observations(engine) == before


def test_set_premise_empty_payload_remains_no_directive() -> None:
    engine = Engine()
    before = _observations(engine)
    d1 = engine.step("set premise")
    assert d1 == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


def test_set_premise_whitespace_payload_remains_no_directive() -> None:
    engine = Engine()
    before = _observations(engine)
    d1 = engine.step("set premise    ")
    assert d1 == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


def test_set_premise_to_variant_remains_no_directive() -> None:
    engine = Engine()

    decision = engine.step("set premise to concise replies")
    assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    _assert_observations(engine, premise=None, policies={})


def test_set_premise_to_with_whitespace_payload_remains_no_directive() -> None:
    engine = Engine()

    decision = engine.step("set premise to   ")

    assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    _assert_observations(engine, premise=None, policies={})


def test_change_premise_requires_existing_premise() -> None:
    engine = Engine()

    d1 = engine.step("change premise to concise")
    assert d1 == {
        "kind": "error",
        "message": "No premise is set.\nUse 'set premise <value>' to define one.",
    }
    _assert_observations(engine, premise=None, policies={})

    engine.step("set premise first")
    d2 = engine.step("change premise to second")
    assert d2["kind"] == DECISION_UPDATE
    assert engine.premise == "second"


def test_change_premise_to_empty_payload_remains_no_directive() -> None:
    engine = Engine()
    engine.step("set premise baseline")
    before = _observations(engine)

    d1 = engine.step("change premise to")
    assert d1 == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


def test_change_premise_to_without_space_payload_and_empty_variant_remain_no_directive() -> None:
    engine = Engine()
    engine.step("set premise baseline")
    before = _observations(engine)

    near_miss = engine.step("change premise baseline")
    assert near_miss == {"kind": DECISION_NO_DIRECTIVE, "message": None}

    decision = engine.step("change premise to")
    assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


def test_change_premise_to_whitespace_payload_remains_no_directive() -> None:
    engine = Engine()
    engine.step("set premise baseline")
    before = _observations(engine)

    d1 = engine.step("change premise to    ")
    assert d1 == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


def test_change_premise_missing_to_variant_is_no_directive() -> None:
    engine = Engine()
    before = _observations(engine)

    decision = engine.step("change premise concise replies")
    assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


def test_change_premise_with_whitespace_after_prefix_remains_no_directive() -> None:
    engine = Engine()
    _import_state(engine, {"premise": "baseline", "policies": {}, "version": 2})

    decision = engine.step("change premise   ")

    assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    _assert_observations(engine, premise="baseline", policies={})


def test_canonical_premise_forms_still_update_normally() -> None:
    engine = Engine()

    first = engine.step("set premise concise replies")
    second = engine.step("change premise to concise bullet points")

    assert first["kind"] == DECISION_UPDATE
    assert second["kind"] == DECISION_UPDATE
    assert engine.premise == "concise bullet points"


def test_clear_premise_and_clear_state() -> None:
    engine = Engine()
    engine.step("set premise use bullets")
    engine.step("use docker")

    d1 = engine.step("clear premise")
    assert d1["kind"] == DECISION_UPDATE
    _assert_observations(engine, premise=None, policies={"docker": "use"})

    d2 = engine.step("clear state")
    assert d2["kind"] == DECISION_UPDATE
    _assert_observations(engine, premise=None, policies={})


def test_policy_directives_and_idempotent_update() -> None:
    engine = Engine()

    d1 = engine.step("use   The Docker")
    assert d1["kind"] == DECISION_UPDATE
    assert dict(engine.policies) == {"the docker": "use"}

    d2 = engine.step("use docker")
    assert d2["kind"] == DECISION_UPDATE
    assert dict(engine.policies) == {"docker": "use", "the docker": "use"}

    d3 = engine.step("prohibit docker")
    assert d3["kind"] == "error"
    assert d3["message"] == (
        '"docker" is currently in use.\nRemove or replace it before prohibiting it.'
    )
    assert dict(engine.policies) == {"docker": "use", "the docker": "use"}

    engine2 = Engine()
    engine2.step("prohibit docker")
    d4 = engine2.step("prohibit docker")
    assert d4["kind"] == "update"
    assert dict(engine2.policies) == {"docker": "prohibit"}

    d5 = engine2.step("use docker")
    assert d5["kind"] == "error"
    assert d5["message"] == (
        '"docker" is currently prohibited.\nRemove or replace it before using it.'
    )
    assert dict(engine2.policies) == {"docker": "prohibit"}


def test_use_empty_payload_remains_no_directive() -> None:
    engine = Engine()
    before = _observations(engine)

    for text in ["use", "use ", "use    "]:
        decision = engine.step(text)
        assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
        assert _observations(engine) == before


def test_prohibit_empty_payload_remains_no_directive() -> None:
    engine = Engine()
    before = _observations(engine)

    for text in ["prohibit", "prohibit ", "prohibit    "]:
        decision = engine.step(text)
        assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
        assert _observations(engine) == before


def test_replace_use_incomplete_payload_remains_no_directive() -> None:
    engine = Engine()
    before = _observations(engine)

    for text in [
        "use x instead of",
        "use x instead of ",
        "use  instead of y",
        "use   instead of y",
        "use instead of y",
    ]:
        decision = engine.step(text)
        assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
        assert _observations(engine) == before


def test_reset_policies_is_update_even_when_already_empty() -> None:
    engine = Engine()
    d1 = engine.step("reset policies")
    assert d1["kind"] == DECISION_UPDATE
    _assert_observations(engine, premise=None, policies={})

    engine.step("use docker")
    d2 = engine.step("reset policies")
    assert d2["kind"] == DECISION_UPDATE
    _assert_observations(engine, premise=None, policies={})


def test_remove_policy_removes_existing_use_policy() -> None:
    engine = Engine()
    engine.step("use docker")

    decision = engine.step("remove policy docker")

    assert decision["kind"] == DECISION_UPDATE
    _assert_observations(engine, premise=None, policies={})


def test_remove_policy_removes_existing_prohibit_policy() -> None:
    engine = Engine()
    engine.step("prohibit docker")

    decision = engine.step("remove policy docker")

    assert decision["kind"] == DECISION_UPDATE
    _assert_observations(engine, premise=None, policies={})


def test_remove_policy_missing_item_is_idempotent_update() -> None:
    engine = Engine()
    engine.step("use docker")
    before = _observations(engine)

    decision = engine.step("remove policy podman")

    assert decision == {"kind": DECISION_UPDATE, "message": None}
    assert _observations(engine) == before


def test_remove_policy_empty_payload_remains_no_directive() -> None:
    engine = Engine()
    before = _observations(engine)

    decision = engine.step("remove policy")

    assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


def test_remove_policy_whitespace_payload_remains_no_directive() -> None:
    engine = Engine()
    before = _observations(engine)

    decision = engine.step("remove policy    ")

    assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


def test_replace_use_success() -> None:
    engine = Engine()
    engine.step("use docker")

    decision = engine.step("use kubectl instead of docker")

    assert decision["kind"] == DECISION_UPDATE
    assert dict(engine.policies) == {"kubectl": "use"}


def test_replace_use_identity_is_noop_update() -> None:
    engine = Engine()
    engine.step("use docker")

    decision = engine.step("use   Docker  instead of docker")

    assert decision["kind"] == DECISION_UPDATE
    _assert_observations(engine, premise=None, policies={"docker": "use"})


def test_replace_use_identity_case_variant_is_noop_update() -> None:
    engine = Engine()
    engine.step("use docker")

    decision = engine.step("use DOCKER instead of docker")

    assert decision["kind"] == DECISION_UPDATE
    _assert_observations(engine, premise=None, policies={"docker": "use"})


def test_replace_use_missing_source_applies_as_use_update() -> None:
    engine = Engine()

    d1 = engine.step("use kubectl instead of docker")
    assert d1 == {
        "kind": "update",
        "message": None,
    }
    _assert_observations(engine, premise=None, policies={"kubectl": "use"})


def test_replace_use_missing_source_yes_followup_is_no_directive() -> None:
    engine = Engine()

    first = engine.step("use kubectl instead of docker")
    assert first == {
        "kind": "update",
        "message": None,
    }
    _assert_observations(engine, premise=None, policies={"kubectl": "use"})

    second = engine.step("yes")
    assert second == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    _assert_observations(engine, premise=None, policies={"kubectl": "use"})


def test_replace_use_missing_source_no_followup_has_no_mutation() -> None:
    engine = Engine()
    engine.step("use kubectl instead of docker")
    before = _observations(engine)

    decision = engine.step("no")
    assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


def test_replace_use_missing_source_still_reports_target_prohibit_when_new_item_prohibited() -> (
    None
):
    engine = Engine()
    engine.step("prohibit kubectl")

    decision = engine.step("use kubectl instead of docker")
    assert decision == {
        "kind": "error",
        "message": (
            '"kubectl" is currently prohibited.\n'
            "Submit explicit directive(s) to remove it or use a different item."
        ),
    }


def test_replace_use_missing_source_ignores_unrelated_existing_policies() -> None:
    engine = Engine()
    engine.step("use python and docker")

    decision = engine.step("use kubectl instead of python")
    assert decision["kind"] == DECISION_UPDATE
    assert dict(engine.policies) == {"kubectl": "use", "python and docker": "use"}


def test_replace_use_missing_source_ignores_other_conflicting_entries() -> None:
    engine = Engine()
    engine.step("use python and docker")
    engine.step("prohibit python tooling")

    decision = engine.step("use kubectl instead of python")
    assert decision["kind"] == DECISION_UPDATE
    assert dict(engine.policies) == {
        "kubectl": "use",
        "python and docker": "use",
        "python tooling": "prohibit",
    }


def test_replace_use_missing_source_with_empty_probe_uses_invalid_prompt() -> None:
    engine = Engine()
    engine.step("use python and docker")

    decision = engine.step("use kubectl instead of the")
    assert decision["kind"] == DECISION_UPDATE
    _assert_observations(
        engine,
        premise=None,
        policies={"kubectl": "use", "python and docker": "use"},
    )


def test_replace_use_ky_prohibit_returns_error_without_mutation() -> None:
    engine = Engine()
    engine.step("prohibit docker")
    engine.step("use pytest")

    first = engine.step("use kubectl instead of docker")
    expected = (
        '"docker" is currently prohibited.\n'
        "Submit explicit directive(s) to remove it or use a different item."
    )
    assert first == {
        "kind": "error",
        "message": expected,
    }
    assert dict(engine.policies) == {"docker": "prohibit", "pytest": "use"}


def test_replace_use_ky_prohibit_yes_does_not_authorize_mutation() -> None:
    engine = Engine()
    engine.step("prohibit docker")
    engine.step("use pytest")
    first = engine.step("use kubectl instead of docker")
    before = _observations(engine)

    assert first["kind"] == "error"
    decision = engine.step("yes")
    assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


def test_replace_use_kx_prohibit_returns_error_without_mutation() -> None:
    engine = Engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")

    first = engine.step("use kubectl instead of docker")
    expected = (
        '"kubectl" is currently prohibited.\n'
        "Submit explicit directive(s) to remove it or use a different item."
    )
    assert first == {
        "kind": "error",
        "message": expected,
    }
    assert dict(engine.policies) == {"docker": "use", "kubectl": "prohibit"}


def test_replace_use_priority_prefers_source_prohibit_error_when_both_prohibit() -> None:
    engine = Engine()
    engine.step("prohibit docker")
    engine.step("prohibit kubectl")

    first = engine.step("use kubectl instead of docker")
    expected = (
        '"docker" is currently prohibited.\n'
        "Submit explicit directive(s) to remove it or use a different item."
    )
    assert first == {
        "kind": "error",
        "message": expected,
    }
    assert dict(engine.policies) == {"docker": "prohibit", "kubectl": "prohibit"}


def test_replace_use_invalid_source_state_prohibit_clarifies_without_mutation() -> None:
    engine = Engine()
    engine.step("prohibit docker")
    engine.step("use pytest")
    before = _observations(engine)

    decision = engine.step("use kubectl instead of docker")
    assert decision == {
        "kind": "error",
        "message": (
            '"docker" is currently prohibited.\n'
            "Submit explicit directive(s) to remove it or use a different item."
        ),
    }
    assert _observations(engine) == before


def test_replace_use_kx_prohibit_no_followup_has_no_mutation() -> None:
    engine = Engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")
    first = engine.step("use kubectl instead of docker")
    before = _observations(engine)

    assert first["kind"] == "error"
    decision = engine.step("no")
    assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


def test_missing_source_replacement_does_not_block_following_directives() -> None:
    engine = Engine()
    first = engine.step("use kubectl instead of docker")
    assert first["kind"] == "update"

    second = engine.step("use docker")
    assert second["kind"] == "update"
    assert dict(engine.policies) == {"docker": "use", "kubectl": "use"}

    third = engine.step("yes")
    assert third == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert dict(engine.policies) == {"docker": "use", "kubectl": "use"}


def test_missing_source_replacement_does_not_suspend_admin_commands() -> None:
    engine = Engine()
    engine.step("use kubectl instead of docker")
    before = (None, {"kubectl": "use"})

    assert _observations(engine) == before

    assert engine.step("clear state")["kind"] == "update"
    assert engine.step("reset policies")["kind"] == "update"
    _assert_observations(engine, premise=None, policies={})

    resolved = engine.step("yes")
    assert resolved == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert dict(engine.policies) == {}


def test_missing_source_replacement_negative_followup_is_no_directive() -> None:
    engine = Engine()
    engine.step("use kubectl instead of docker")

    decision = engine.step("no")

    assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert dict(engine.policies) == {"kubectl": "use"}


def test_missing_source_replacement_affirmative_followup_tokens_are_no_directive() -> None:
    engine = Engine()
    engine.step("use kubectl instead of docker")

    decision = engine.step("  YES!!!  ")
    assert decision["kind"] == DECISION_NO_DIRECTIVE
    assert dict(engine.policies) == {"kubectl": "use"}


def test_missing_source_replacement_affirmative_token_variants_are_no_directive() -> None:
    for token in ["yes please", "Yep", "yeah", "ok", "  OKAY...  ", "sure!"]:
        engine = Engine()
        engine.step("use kubectl instead of docker")
        decision = engine.step(token)
        assert decision["kind"] == DECISION_NO_DIRECTIVE
        assert dict(engine.policies) == {"kubectl": "use"}


def test_missing_source_replacement_negative_tokens_are_no_directive() -> None:
    engine = Engine()
    engine.step("use kubectl instead of docker")
    before = _observations(engine)

    decision = engine.step("  NO!!!  ")
    assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


def test_missing_source_replacement_no_thanks_is_no_directive() -> None:
    engine = Engine()
    engine.step("use kubectl instead of docker")
    before = _observations(engine)

    decision = engine.step("no thanks.")
    assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


def test_missing_source_replacement_negative_token_variants_are_no_directive() -> None:
    for token in ["nope", "Nope??", " no ", "NO THANKS!"]:
        engine = Engine()
        engine.step("use kubectl instead of docker")
        before = _observations(engine)
        decision = engine.step(token)
        assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
        assert _observations(engine) == before


def test_missing_source_replacement_unmatched_followup_is_no_directive() -> None:
    engine = Engine()
    engine.step("use kubectl instead of docker")
    before = _observations(engine)

    second = engine.step("maybe")
    assert second == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


def test_missing_source_replacement_unmatched_followups_remain_no_directive() -> None:
    engine = Engine()
    engine.step("use kubectl instead of docker")
    before = _observations(engine)

    assert engine.step("later") == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert engine.step("still later") == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


def test_prohibited_replacement_yes_cannot_override_conflicting_target_polarity() -> None:
    engine = Engine()
    engine.step("use docker")
    engine.step("prohibit kubectl")

    first = engine.step("use kubectl instead of docker")
    assert first["kind"] == "error"
    assert dict(engine.policies) == {"docker": "use", "kubectl": "prohibit"}

    second = engine.step("yes")
    assert second["kind"] == DECISION_NO_DIRECTIVE
    assert dict(engine.policies) == {"docker": "use", "kubectl": "prohibit"}


def test_import_json_does_not_change_independent_yes_no_followup_behavior() -> None:
    engine = Engine()
    first = engine.step("use kubectl instead of docker")
    assert first["kind"] == DECISION_UPDATE

    imported = {"premise": "baseline", "policies": {"pytest": "use"}, "version": 2}
    engine.import_json(json.dumps(imported))

    yes_decision = engine.step("yes")
    assert yes_decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    _assert_observations(engine, premise="baseline", policies={"pytest": "use"})

    no_decision = engine.step("no")
    assert no_decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}


def test_remove_policy_uses_normalized_item_matching() -> None:
    engine = Engine()
    engine.step("use The Docker")

    decision = engine.step("remove policy the docker")
    assert decision["kind"] == DECISION_UPDATE
    _assert_observations(engine, premise=None, policies={})


def test_use_and_prohibit_article_variants_remain_distinct_policies() -> None:
    engine = Engine()

    first = engine.step("use docker")
    second = engine.step("prohibit the docker")

    assert first == {"kind": DECISION_UPDATE, "message": None}
    assert second == {"kind": DECISION_UPDATE, "message": None}
    _assert_observations(
        engine,
        premise=None,
        policies={"docker": "use", "the docker": "prohibit"},
    )


def test_remove_policy_the_docker_does_not_remove_docker() -> None:
    engine = Engine()
    engine.step("use docker")

    decision = engine.step("remove policy the docker")

    assert decision == {"kind": DECISION_UPDATE, "message": None}
    _assert_observations(engine, premise=None, policies={"docker": "use"})


def test_dont_and_dont_apostrophe_remain_distinct_policy_identities() -> None:
    engine = Engine()

    first = engine.step("use don't")
    second = engine.step("prohibit dont")

    assert first == {"kind": DECISION_UPDATE, "message": None}
    assert second == {"kind": DECISION_UPDATE, "message": None}
    _assert_observations(
        engine,
        premise=None,
        policies={"don't": "use", "dont": "prohibit"},
    )


def test_import_json_preserves_distinct_article_variant_policy_keys() -> None:
    engine = Engine()

    engine.import_json(
        json.dumps(
            {
                "premise": None,
                "policies": {"docker": "use", " The Docker ": "prohibit"},
                "version": 2,
            }
        )
    )

    _assert_observations(
        engine,
        premise=None,
        policies={"docker": "use", "the docker": "prohibit"},
    )


def test_import_json_preserves_distinct_dont_and_dont_apostrophe_policy_keys() -> None:
    engine = Engine()

    engine.import_json(
        json.dumps(
            {
                "premise": None,
                "policies": {"dont": "prohibit", "don't": "use"},
                "version": 2,
            }
        )
    )

    _assert_observations(
        engine,
        premise=None,
        policies={"don't": "use", "dont": "prohibit"},
    )


def test_export_import_round_trip_preserves_distinct_normalized_policy_keys() -> None:
    source = Engine()
    source.import_json(
        json.dumps(
            {
                "premise": None,
                "policies": {
                    "docker": "use",
                    "the docker": "prohibit",
                    "dont": "prohibit",
                    "don't": "use",
                },
                "version": 2,
            }
        )
    )

    payload = source.export_json()

    restored = Engine()
    restored.import_json(payload)

    assert dict(restored.policies) == {
        "docker": "use",
        "don't": "use",
        "dont": "prohibit",
        "the docker": "prohibit",
    }


@pytest.mark.parametrize(
    ("user_input", "initial_state"),
    [
        ("use docker and prohibit peanuts", {"premise": None, "policies": {}, "version": 2}),
        ("use docker or prohibit peanuts", {"premise": None, "policies": {}, "version": 2}),
        ("use docker xor prohibit peanuts", {"premise": None, "policies": {}, "version": 2}),
        ("use docker but prohibit peanuts", {"premise": None, "policies": {}, "version": 2}),
        ("use docker; prohibit peanuts", {"premise": None, "policies": {}, "version": 2}),
        ("use docker. prohibit peanuts", {"premise": None, "policies": {}, "version": 2}),
        (
            "use docker for development and prohibit peanuts",
            {"premise": None, "policies": {}, "version": 2},
        ),
        (
            "set premise vegetarian curry and prohibit peanuts",
            {"premise": None, "policies": {}, "version": 2},
        ),
        (
            "change premise to vegan curry or use docker",
            {"premise": "baseline", "policies": {}, "version": 2},
        ),
        (
            "remove policy docker and use podman",
            {"premise": None, "policies": {"docker": "use"}, "version": 2},
        ),
        (
            "clear premise and prohibit peanuts",
            {"premise": "baseline", "policies": {}, "version": 2},
        ),
        (
            "reset policies; use docker",
            {"premise": None, "policies": {"docker": "prohibit"}, "version": 2},
        ),
        (
            "clear state then set premise new project",
            {"premise": "baseline", "policies": {"docker": "use"}, "version": 2},
        ),
        (
            'use "docker and prohibit peanuts"',
            {"premise": None, "policies": {}, "version": 2},
        ),
        (
            'set premise "use docker and prohibit peanuts"',
            {"premise": None, "policies": {}, "version": 2},
        ),
        (
            "use docker instead of prohibit peanuts",
            {"premise": None, "policies": {}, "version": 2},
        ),
    ],
)
def test_compound_directives_remain_no_directive_without_mutation(
    user_input: str, initial_state: dict[str, object]
) -> None:
    engine = Engine()
    _import_state(engine, initial_state)
    before = _observations(engine)

    decision = engine.step(user_input)

    assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


def test_quoted_non_directive_leading_input_remains_no_directive() -> None:
    engine = Engine()

    decision = engine.step('"use docker and prohibit peanuts"')

    assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    _assert_observations(engine, premise=None, policies={})


@pytest.mark.parametrize(
    ("user_input", "initial_state", "expected_decision_kind", "expected_state"),
    [
        (
            "use docker for prohibitively expensive builds",
            {"premise": None, "policies": {}, "version": 2},
            "update",
            {
                "premise": None,
                "policies": {"docker for prohibitively expensive builds": "use"},
                "version": 2,
            },
        ),
        (
            "set premise reusable docker-prohibit-safe workflow",
            {"premise": None, "policies": {}, "version": 2},
            "update",
            {"premise": "reusable docker-prohibit-safe workflow", "policies": {}, "version": 2},
        ),
        (
            "change premise to reset policieset ownership",
            {"premise": "baseline", "policies": {}, "version": 2},
            "update",
            {"premise": "reset policieset ownership", "policies": {}, "version": 2},
        ),
        (
            "remove policy clear stateful systems",
            {"premise": None, "policies": {"docker": "use"}, "version": 2},
            "update",
            {"premise": None, "policies": {"docker": "use"}, "version": 2},
        ),
    ],
)
def test_directive_like_substrings_inside_larger_words_do_not_trigger_compound_rejection(
    user_input: str,
    initial_state: dict[str, object],
    expected_decision_kind: str,
    expected_state: dict[str, object],
) -> None:
    engine = Engine()
    _import_state(engine, initial_state)

    decision = engine.step(user_input)

    assert decision["kind"] != DECISION_ERROR
    assert decision["kind"] == expected_decision_kind
    _assert_observations(
        engine,
        premise=expected_state["premise"],
        policies=expected_state["policies"],
    )


@pytest.mark.parametrize(
    ("user_input", "initial_state", "expected_state"),
    [
        (
            "use docker",
            {"premise": None, "policies": {}, "version": 2},
            {"premise": None, "policies": {"docker": "use"}, "version": 2},
        ),
        (
            "prohibit peanuts",
            {"premise": None, "policies": {}, "version": 2},
            {"premise": None, "policies": {"peanuts": "prohibit"}, "version": 2},
        ),
        (
            "set premise vegetarian curry",
            {"premise": None, "policies": {}, "version": 2},
            {"premise": "vegetarian curry", "policies": {}, "version": 2},
        ),
        (
            "change premise to vegan curry",
            {"premise": "vegetarian curry", "policies": {}, "version": 2},
            {"premise": "vegan curry", "policies": {}, "version": 2},
        ),
        (
            "remove policy docker",
            {"premise": None, "policies": {"docker": "use"}, "version": 2},
            {"premise": None, "policies": {}, "version": 2},
        ),
        (
            "clear premise",
            {"premise": "vegetarian curry", "policies": {}, "version": 2},
            {"premise": None, "policies": {}, "version": 2},
        ),
        (
            "reset policies",
            {"premise": None, "policies": {"docker": "use"}, "version": 2},
            {"premise": None, "policies": {}, "version": 2},
        ),
        (
            "clear state",
            {"premise": "baseline", "policies": {"docker": "use"}, "version": 2},
            {"premise": None, "policies": {}, "version": 2},
        ),
        (
            "use docker instead of podman",
            {"premise": None, "policies": {"podman": "use"}, "version": 2},
            {"premise": None, "policies": {"docker": "use"}, "version": 2},
        ),
    ],
)
def test_valid_single_directives_still_work(
    user_input: str, initial_state: dict[str, object], expected_state: dict[str, object]
) -> None:
    engine = Engine()
    _import_state(engine, initial_state)

    decision = engine.step(user_input)

    assert decision == {
        "kind": DECISION_UPDATE,
        "message": None,
    }
    _assert_observations(
        engine,
        premise=expected_state["premise"],
        policies=expected_state["policies"],
    )


@pytest.mark.parametrize(
    "directive_start",
    [
        "set premise vegetarian curry",
        "change premise to vegan curry",
        "use docker",
        "prohibit peanuts",
        "remove policy docker",
        "use docker instead of podman",
        "clear premise",
        "reset policies",
        "clear state",
    ],
)
def test_all_canonical_directive_starts_remain_single_directive_when_valid(
    directive_start: str,
) -> None:
    engine = Engine()
    _import_state(engine, {"premise": "baseline", "policies": {"podman": "use"}, "version": 2})

    decision = engine.step(directive_start)

    assert decision["kind"] != DECISION_NO_DIRECTIVE


def test_compound_no_directive_after_prior_missing_source_replacement_update() -> None:
    engine = Engine()
    first = engine.step("use kubectl instead of docker")
    assert first == {
        "kind": DECISION_UPDATE,
        "message": None,
    }

    decision = engine.step("use docker and prohibit peanuts")

    assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    _assert_observations(engine, premise=None, policies={"kubectl": "use"})
