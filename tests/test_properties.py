import json
import re
from copy import deepcopy
from unicodedata import normalize as unicode_normalize

from hypothesis import assume, given
from hypothesis import strategies as st

from context_compiler import DECISION_ERROR, DECISION_NO_DIRECTIVE, DECISION_UPDATE, create_engine
from context_compiler.grammar import (
    DirectiveKind,
    decompose_directive,
    match_canonical_directive_start,
    render_directive,
)


def _observations(engine: object) -> tuple[object, dict[str, object]]:
    return engine.premise, dict(engine.policies)


def _run_sequence(inputs: list[str]) -> tuple[object, dict[str, object]]:
    engine = create_engine()
    for item in inputs:
        engine.step(item)
    return _observations(engine)


def _normalize_item_like_engine(value: str) -> str:
    normalized = unicode_normalize("NFKC", value)
    normalized = normalized.replace("’", "'").replace("`", "'")
    normalized = normalized.lower()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _is_stable_policy_key_like_engine(value: str) -> bool:
    normalized = _normalize_item_like_engine(value)
    return normalized != "" and _normalize_item_like_engine(normalized) == normalized


def _contains_canonical_start_fragment(value: str) -> bool:
    for start in range(len(value)):
        if match_canonical_directive_start(value, start) is not None:
            return True
    return False


def _sanitize_premise_like_engine(value: str) -> str:
    sanitized = unicode_normalize("NFKC", value)
    sanitized = sanitized.replace("’", "'").replace("`", "'")
    return re.sub(r"\s+", " ", sanitized).strip()


NORMALIZATION_SENSITIVE_TEXT = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),
        blacklist_characters="\x00",
    )
    | st.sampled_from([" ", "\t", "’", "`"]),
    min_size=1,
    max_size=20,
)

POLICY_VALUE = st.sampled_from(["use", "prohibit"])

VALID_STATE_PAYLOADS = st.builds(
    lambda premise, pairs: {
        "premise": premise,
        "policies": dict(pairs),
        "version": 2,
    },
    premise=st.one_of(st.none(), NORMALIZATION_SENSITIVE_TEXT),
    pairs=st.lists(
        st.tuples(NORMALIZATION_SENSITIVE_TEXT, POLICY_VALUE),
        min_size=0,
        max_size=8,
    ),
).filter(lambda payload: all(_is_stable_policy_key_like_engine(key) for key in payload["policies"]))


VALID_NONEMPTY_ITEM_TEXT = NORMALIZATION_SENSITIVE_TEXT.filter(
    lambda value: (
        _normalize_item_like_engine(value) != ""
        and not _contains_canonical_start_fragment(value)
        and " instead of " not in value
        and not value.startswith("instead of ")
        and not value.endswith(" instead of")
    )
)

VALID_USE_ITEM_TEXT = VALID_NONEMPTY_ITEM_TEXT.filter(
    lambda value: decompose_directive(f"use {value}") is not None
)

VALID_PROHIBIT_ITEM_TEXT = VALID_NONEMPTY_ITEM_TEXT.filter(
    lambda value: decompose_directive(f"prohibit {value}") is not None
)

VALID_PREMISE_TEXT = NORMALIZATION_SENSITIVE_TEXT.filter(
    lambda value: _sanitize_premise_like_engine(value) != ""
)

CANONICAL_GRAMMAR_PREMISE_TEXT = NORMALIZATION_SENSITIVE_TEXT.map(
    _sanitize_premise_like_engine
).filter(
    lambda value: (
        value != ""
        and decompose_directive(f"set premise {value}") is not None
        and decompose_directive(f"change premise to {value}") is not None
    )
)

CANONICAL_GRAMMAR_ITEM_TEXT = NORMALIZATION_SENSITIVE_TEXT.map(_normalize_item_like_engine).filter(
    lambda value: (
        value != ""
        and decompose_directive(f"use {value}") is not None
        and decompose_directive(f"prohibit {value}") is not None
        and decompose_directive(f"remove policy {value}") is not None
    )
)


def _build_deterministic_replacement_case(
    premise: str | None,
    unrelated_pairs: list[tuple[str, str]],
    new_item: str,
    old_item: str,
    old_present: bool,
    new_present: bool,
) -> dict[str, object]:
    new_key = _normalize_item_like_engine(new_item)
    old_key = _normalize_item_like_engine(old_item)

    policies = {key: value for key, value in unrelated_pairs if key not in {new_key, old_key}}
    if old_present:
        policies[old_key] = "use"
    if new_present:
        policies[new_key] = "use"

    return {
        "initial_state": {
            "premise": premise,
            "policies": dict(sorted(policies.items())),
            "version": 2,
        },
        "new_item": new_item,
        "old_item": old_item,
        "old_present": old_present,
    }


DETERMINISTIC_REPLACEMENT_CASES = (
    st.tuples(
        st.one_of(st.none(), VALID_PREMISE_TEXT.map(_sanitize_premise_like_engine)),
        st.lists(
            st.tuples(CANONICAL_GRAMMAR_ITEM_TEXT, POLICY_VALUE),
            min_size=0,
            max_size=6,
        ),
        VALID_USE_ITEM_TEXT,
        VALID_NONEMPTY_ITEM_TEXT,
        st.booleans(),
        st.booleans(),
    )
    .filter(
        lambda args: (
            _normalize_item_like_engine(args[2]) != _normalize_item_like_engine(args[3])
            and decompose_directive(f"use {args[2]} instead of {args[3]}") is not None
            and not any(
                key in {_normalize_item_like_engine(args[2]), _normalize_item_like_engine(args[3])}
                and value == "prohibit"
                for key, value in args[1]
            )
        )
    )
    .map(lambda args: _build_deterministic_replacement_case(*args))
)


def _payload_has_stable_export_import_cycle(payload: dict[str, object]) -> bool:
    engine = create_engine()
    engine.import_json(json.dumps(payload))
    exported = engine.export_json()

    restored = create_engine()
    try:
        restored.import_json(exported)
    except ValueError:
        return False

    return _observations(restored) == _observations(engine)


GRAMMAR_RENDER_CASES = st.one_of(
    CANONICAL_GRAMMAR_PREMISE_TEXT.map(
        lambda value: {"kind": DirectiveKind.SET_PREMISE, "operands": {"value": value}}
    ),
    CANONICAL_GRAMMAR_PREMISE_TEXT.map(
        lambda value: {"kind": DirectiveKind.CHANGE_PREMISE, "operands": {"value": value}}
    ),
    CANONICAL_GRAMMAR_ITEM_TEXT.map(
        lambda item: {"kind": DirectiveKind.USE_ITEM, "operands": {"item": item}}
    ),
    CANONICAL_GRAMMAR_ITEM_TEXT.map(
        lambda item: {"kind": DirectiveKind.PROHIBIT_ITEM, "operands": {"item": item}}
    ),
    CANONICAL_GRAMMAR_ITEM_TEXT.map(
        lambda item: {"kind": DirectiveKind.REMOVE_POLICY, "operands": {"item": item}}
    ),
    st.tuples(CANONICAL_GRAMMAR_ITEM_TEXT, CANONICAL_GRAMMAR_ITEM_TEXT)
    .filter(
        lambda pair: _normalize_item_like_engine(pair[0]) != _normalize_item_like_engine(pair[1])
    )
    .map(
        lambda pair: {
            "kind": DirectiveKind.REPLACE_USE,
            "operands": {"new_item": pair[0], "old_item": pair[1]},
        }
    ),
    st.sampled_from(
        [
            {"kind": DirectiveKind.CLEAR_PREMISE, "operands": {}},
            {"kind": DirectiveKind.RESET_POLICIES, "operands": {}},
            {"kind": DirectiveKind.CLEAR_STATE, "operands": {}},
        ]
    ),
)


@given(st.lists(st.text(max_size=40), min_size=0, max_size=20))
def test_determinism_same_input_sequence_same_state(inputs: list[str]) -> None:
    assert _run_sequence(inputs) == _run_sequence(inputs)


@given(GRAMMAR_RENDER_CASES)
def test_grammar_helper_render_validate_round_trip_is_stable(
    case: dict[str, DirectiveKind | dict[str, str]],
) -> None:
    kind = case["kind"]
    operands = case["operands"]

    assert isinstance(kind, DirectiveKind)
    assert isinstance(operands, dict)

    rendered = render_directive(kind, **operands)
    directive = decompose_directive(rendered)

    assert directive is not None
    assert directive.kind is kind
    assert directive.text == rendered
    assert decompose_directive(directive.text) == directive
    assert render_directive(kind, **operands) == rendered


@given(st.text(min_size=1, max_size=30))
def test_idempotent_use_item_is_update_and_stable_state(item: str) -> None:
    assume(" instead of " not in item)
    assume(not item.startswith("instead of "))
    assume(not item.endswith(" instead of"))
    assume(_normalize_item_like_engine(item) != "")
    assume(not _contains_canonical_start_fragment(item))
    assume(decompose_directive(f"use {item}") is not None)
    engine = create_engine()
    d1 = engine.step(f"use {item}")
    d2 = engine.step(f"use {item}")

    assert d1["kind"] == "update"
    assert d2["kind"] == "update"
    assert len(engine.policies) == 1


@given(item=st.text(alphabet=" \t", min_size=0, max_size=6))
def test_use_item_with_whitespace_only_payload_remains_no_directive(item: str) -> None:
    assert _normalize_item_like_engine(item) == ""
    engine = create_engine()
    before = _observations(engine)

    d1 = engine.step(f"use {item}")
    d2 = engine.step(f"use {item}")

    assert d1 == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert d2 == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


@given(st.text(min_size=1, max_size=30))
def test_idempotent_prohibit_item_is_update_and_stable_state(item: str) -> None:
    assume(_normalize_item_like_engine(item) != "")
    assume(not _contains_canonical_start_fragment(item))
    assume(decompose_directive(f"prohibit {item}") is not None)
    engine = create_engine()
    d1 = engine.step(f"prohibit {item}")
    d2 = engine.step(f"prohibit {item}")

    assert d1["kind"] == DECISION_UPDATE
    assert d2["kind"] == DECISION_UPDATE
    assert len(engine.policies) == 1


@given(item=st.text(alphabet=" \t", min_size=0, max_size=6))
def test_prohibit_item_with_whitespace_only_payload_remains_no_directive(item: str) -> None:
    assert _normalize_item_like_engine(item) == ""
    engine = create_engine()
    before = _observations(engine)

    d1 = engine.step(f"prohibit {item}")
    d2 = engine.step(f"prohibit {item}")

    assert d1 == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert d2 == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


@given(st.lists(st.text(max_size=80), min_size=0, max_size=20))
def test_non_matching_inputs_can_remain_no_directive_only(inputs: list[str]) -> None:
    engine = create_engine()
    before = _observations(engine)

    for text in inputs:
        decision = engine.step(f"please {text}")
        assert decision["kind"] == DECISION_NO_DIRECTIVE

    assert _observations(engine) == before


@given(st.lists(st.text(max_size=50), min_size=0, max_size=30))
def test_no_directive_sequence_preserves_state_and_decision_kind(inputs: list[str]) -> None:
    engine = create_engine()
    before = _observations(engine)

    for text in inputs:
        decision = engine.step(f"prefix {text}")
        assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
        assert _observations(engine) == before


@given(st.text(min_size=1, max_size=30))
def test_contradiction_use_after_prohibit_always_clarifies(item: str) -> None:
    assume(not _contains_canonical_start_fragment(item))
    assume(decompose_directive(f"prohibit {item}") is not None)
    assume(decompose_directive(f"use {item}") is not None)
    engine = create_engine()
    engine.step(f"prohibit {item}")
    before = _observations(engine)

    decision = engine.step(f"use {item}")
    assert decision["kind"] == DECISION_ERROR
    assert _observations(engine) == before


@given(st.text(min_size=1, max_size=30))
def test_contradiction_prohibit_after_use_always_clarifies(item: str) -> None:
    assume(" instead of " not in item)
    assume(not item.startswith("instead of "))
    assume(not item.endswith(" instead of"))
    assume(not _contains_canonical_start_fragment(item))
    assume(decompose_directive(f"use {item}") is not None)
    assume(decompose_directive(f"prohibit {item}") is not None)
    engine = create_engine()
    engine.step(f"use {item}")
    before = _observations(engine)

    decision = engine.step(f"prohibit {item}")
    assert decision["kind"] == DECISION_ERROR
    assert _observations(engine) == before


@given(VALID_STATE_PAYLOADS)
def test_export_import_round_trip_preserves_authoritative_state_for_generated_payloads(
    payload: dict[str, object],
) -> None:
    source = create_engine()
    source.import_json(json.dumps(payload))
    canonical_state = _observations(source)

    target = create_engine()
    target.import_json(source.export_json())

    assert _observations(target) == canonical_state


@given(VALID_STATE_PAYLOADS, st.integers(min_value=1, max_value=5))
def test_repeated_export_import_cycles_remain_stable(
    payload: dict[str, object], cycles: int
) -> None:
    engine = create_engine()
    engine.import_json(json.dumps(payload))

    expected_state = _observations(engine)
    expected_json = engine.export_json()

    for _ in range(cycles):
        next_engine = create_engine()
        next_engine.import_json(expected_json)
        assert _observations(next_engine) == expected_state
        assert next_engine.export_json() == expected_json
        expected_state = _observations(next_engine)
        expected_json = next_engine.export_json()


@given(DETERMINISTIC_REPLACEMENT_CASES)
def test_deterministic_replacement_matches_equivalent_explicit_transition(
    case: dict[str, object],
) -> None:
    initial_state = case["initial_state"]
    new_item = case["new_item"]
    old_item = case["old_item"]
    old_present = case["old_present"]

    assert isinstance(initial_state, dict)
    assert isinstance(new_item, str)
    assert isinstance(old_item, str)
    assert isinstance(old_present, bool)

    oracle_engine = create_engine()
    oracle_engine.import_json(
        json.dumps(deepcopy(initial_state), sort_keys=True, separators=(",", ":"))
    )
    oracle_engine.step(f"remove policy {old_item}")
    expected_decision = oracle_engine.step(f"use {new_item}")
    expected_state = _observations(oracle_engine)

    engine = create_engine()
    engine.import_json(json.dumps(initial_state, sort_keys=True, separators=(",", ":")))
    decision = engine.step(f"use {new_item} instead of {old_item}")

    assert expected_decision == {
        "kind": DECISION_UPDATE,
        "message": None,
    }
    assert decision == expected_decision
    assert _observations(engine) == expected_state

    if not old_present:
        followup = engine.step("yes")
        assert followup == {"kind": DECISION_NO_DIRECTIVE, "message": None}
        assert _observations(engine) == expected_state
