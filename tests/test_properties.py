import json
import re
from copy import deepcopy
from unicodedata import normalize as unicode_normalize

from hypothesis import assume, given
from hypothesis import strategies as st

import context_compiler.grammar as grammar_module
from context_compiler import (
    DECISION_ERROR,
    DECISION_NO_DIRECTIVE,
    DECISION_UPDATE,
    Engine,
)
from context_compiler.grammar import (
    CanonicalDirective,
    DirectiveKind,
    DirectiveSyntaxFailure,
    InvalidDirectiveSyntax,
    decompose_directive,
    get_directive_metadata,
)


def _observations(engine: object) -> tuple[object, dict[str, object]]:
    return engine.premise, dict(engine.policies)


def _run_sequence(inputs: list[str]) -> tuple[object, dict[str, object]]:
    engine = Engine()
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
        if grammar_module._match_canonical_directive_start(value, start) is not None:
            return True
    return False


def _is_canonical_directive(value: object) -> bool:
    return isinstance(value, CanonicalDirective)


def _sanitize_premise_like_engine(value: str) -> str:
    sanitized = unicode_normalize("NFKC", value)
    sanitized = sanitized.replace("’", "'").replace("`", "'")
    return re.sub(r"\s+", " ", sanitized).strip()


def _canonical_directive_from_text(text: str) -> CanonicalDirective:
    directive = decompose_directive(text)
    assert isinstance(directive, CanonicalDirective)
    return directive


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
    lambda value: _is_canonical_directive(decompose_directive(f"use {value}"))
)

VALID_PROHIBIT_ITEM_TEXT = VALID_NONEMPTY_ITEM_TEXT.filter(
    lambda value: _is_canonical_directive(decompose_directive(f"prohibit {value}"))
)

VALID_PREMISE_TEXT = NORMALIZATION_SENSITIVE_TEXT.filter(
    lambda value: _sanitize_premise_like_engine(value) != ""
)

CANONICAL_GRAMMAR_PREMISE_TEXT = NORMALIZATION_SENSITIVE_TEXT.map(
    _sanitize_premise_like_engine
).filter(
    lambda value: (
        value != ""
        and _is_canonical_directive(decompose_directive(f"set premise {value}"))
        and _is_canonical_directive(decompose_directive(f"change premise to {value}"))
    )
)

CANONICAL_GRAMMAR_ITEM_TEXT = NORMALIZATION_SENSITIVE_TEXT.map(_normalize_item_like_engine).filter(
    lambda value: (
        value != ""
        and _is_canonical_directive(decompose_directive(f"use {value}"))
        and _is_canonical_directive(decompose_directive(f"prohibit {value}"))
        and _is_canonical_directive(decompose_directive(f"remove policy {value}"))
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
            and _is_canonical_directive(decompose_directive(f"use {args[2]} instead of {args[3]}"))
            and not any(
                key in {_normalize_item_like_engine(args[2]), _normalize_item_like_engine(args[3])}
                and value == "prohibit"
                for key, value in args[1]
            )
        )
    )
    .filter(lambda args: args[4])
    .map(lambda args: _build_deterministic_replacement_case(*args))
)

ERROR_CASES = st.one_of(
    CANONICAL_GRAMMAR_PREMISE_TEXT.map(
        lambda value: (
            {"premise": "existing", "policies": {}, "version": 2},
            _canonical_directive_from_text(f"set premise {value}"),
        )
    ),
    CANONICAL_GRAMMAR_PREMISE_TEXT.map(
        lambda value: (
            {"premise": None, "policies": {}, "version": 2},
            _canonical_directive_from_text(f"change premise to {value}"),
        )
    ),
    CANONICAL_GRAMMAR_ITEM_TEXT.map(
        lambda item: (
            {
                "premise": None,
                "policies": {_normalize_item_like_engine(item): "prohibit"},
                "version": 2,
            },
            _canonical_directive_from_text(f"use {item}"),
        )
    ),
    CANONICAL_GRAMMAR_ITEM_TEXT.map(
        lambda item: (
            {"premise": None, "policies": {_normalize_item_like_engine(item): "use"}, "version": 2},
            _canonical_directive_from_text(f"prohibit {item}"),
        )
    ),
    st.tuples(VALID_USE_ITEM_TEXT, VALID_NONEMPTY_ITEM_TEXT)
    .filter(
        lambda pair: _normalize_item_like_engine(pair[0]) != _normalize_item_like_engine(pair[1])
    )
    .filter(
        lambda pair: _is_canonical_directive(
            decompose_directive(f"use {pair[0]} instead of {pair[1]}")
        )
    )
    .map(
        lambda pair: (
            {"premise": None, "policies": {}, "version": 2},
            _canonical_directive_from_text(f"use {pair[0]} instead of {pair[1]}"),
        )
    ),
)

REPLACEMENT_ERROR_CASES = st.one_of(
    st.tuples(CANONICAL_GRAMMAR_ITEM_TEXT, CANONICAL_GRAMMAR_ITEM_TEXT)
    .filter(
        lambda pair: _normalize_item_like_engine(pair[0]) != _normalize_item_like_engine(pair[1])
    )
    .map(
        lambda pair: (
            {
                "premise": None,
                "policies": {_normalize_item_like_engine(pair[1]): "prohibit"},
                "version": 2,
            },
            pair[0],
            pair[1],
            "source_prohibited",
        )
    ),
    st.tuples(CANONICAL_GRAMMAR_ITEM_TEXT, CANONICAL_GRAMMAR_ITEM_TEXT)
    .filter(
        lambda pair: _normalize_item_like_engine(pair[0]) != _normalize_item_like_engine(pair[1])
    )
    .map(
        lambda pair: (
            {
                "premise": None,
                "policies": {_normalize_item_like_engine(pair[0]): "prohibit"},
                "version": 2,
            },
            pair[0],
            pair[1],
            "target_prohibited",
        )
    ),
    st.tuples(VALID_USE_ITEM_TEXT, VALID_NONEMPTY_ITEM_TEXT)
    .filter(
        lambda pair: _normalize_item_like_engine(pair[0]) != _normalize_item_like_engine(pair[1])
    )
    .map(
        lambda pair: (
            {"premise": None, "policies": {}, "version": 2},
            pair[0],
            pair[1],
            "source_absent",
        )
    ),
)

POLICY_MACHINE_OPERATIONS = st.one_of(
    CANONICAL_GRAMMAR_ITEM_TEXT.map(lambda item: ("use", item)),
    CANONICAL_GRAMMAR_ITEM_TEXT.map(lambda item: ("prohibit", item)),
    CANONICAL_GRAMMAR_ITEM_TEXT.map(lambda item: ("remove", item)),
    st.tuples(CANONICAL_GRAMMAR_ITEM_TEXT, CANONICAL_GRAMMAR_ITEM_TEXT).map(
        lambda pair: ("replace", pair[0], pair[1])
    ),
)

PREMISE_MACHINE_OPERATIONS = st.one_of(
    CANONICAL_GRAMMAR_PREMISE_TEXT.map(lambda value: ("set", value)),
    CANONICAL_GRAMMAR_PREMISE_TEXT.map(lambda value: ("change", value)),
    st.sampled_from([("clear_premise",), ("clear_state",)]),
)

CANONICAL_DIRECTIVE_TEXT_CASES = st.one_of(
    CANONICAL_GRAMMAR_PREMISE_TEXT.map(lambda value: f"set premise {value}"),
    CANONICAL_GRAMMAR_PREMISE_TEXT.map(lambda value: f"change premise to {value}"),
    CANONICAL_GRAMMAR_ITEM_TEXT.map(lambda item: f"use {item}"),
    CANONICAL_GRAMMAR_ITEM_TEXT.map(lambda item: f"prohibit {item}"),
    CANONICAL_GRAMMAR_ITEM_TEXT.map(lambda item: f"remove policy {item}"),
    st.tuples(CANONICAL_GRAMMAR_ITEM_TEXT, CANONICAL_GRAMMAR_ITEM_TEXT)
    .filter(
        lambda pair: _normalize_item_like_engine(pair[0]) != _normalize_item_like_engine(pair[1])
    )
    .map(lambda pair: f"use {pair[0]} instead of {pair[1]}"),
    st.sampled_from(["clear premise", "reset policies", "clear state"]),
)

NONEMPTY_NORMALIZED_KEY_TEXT = NORMALIZATION_SENSITIVE_TEXT.filter(
    lambda value: _normalize_item_like_engine(value) != ""
)

INVALID_EMPTY_NORMALIZED_KEY_TEXT = st.text(alphabet=" \t", min_size=1, max_size=6)

EQUIVALENT_NORMALIZED_KEY_PAIRS = st.builds(
    lambda item: (item, "  " + item.upper().replace("'", "’") + "  "),
    CANONICAL_GRAMMAR_ITEM_TEXT,
)


def _payload_has_stable_export_import_cycle(payload: dict[str, object]) -> bool:
    engine = Engine()
    engine.import_json(json.dumps(payload))
    exported = engine.export_json()

    restored = Engine()
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

REPLACEMENT_NEAR_MISS_CASES = st.one_of(
    VALID_NONEMPTY_ITEM_TEXT.map(lambda old_item: f"use instead of {old_item}"),
    VALID_USE_ITEM_TEXT.map(lambda new_item: f"use {new_item} instead of"),
    st.tuples(VALID_USE_ITEM_TEXT, VALID_NONEMPTY_ITEM_TEXT, VALID_NONEMPTY_ITEM_TEXT)
    .filter(
        lambda parts: (
            _normalize_item_like_engine(parts[0]) != _normalize_item_like_engine(parts[1])
            and _normalize_item_like_engine(parts[0]) != _normalize_item_like_engine(parts[2])
            and _normalize_item_like_engine(parts[1]) != _normalize_item_like_engine(parts[2])
        )
    )
    .map(lambda parts: f"use {parts[0]} instead of {parts[1]} instead of {parts[2]}"),
)


@given(st.lists(st.text(max_size=40), min_size=0, max_size=20))
def test_determinism_same_input_sequence_same_state(inputs: list[str]) -> None:
    assert _run_sequence(inputs) == _run_sequence(inputs)


@given(VALID_STATE_PAYLOADS, CANONICAL_DIRECTIVE_TEXT_CASES)
def test_step_and_apply_directive_are_equivalent_for_canonical_inputs(
    initial_state: dict[str, object],
    text: str,
) -> None:
    directive = decompose_directive(text)
    assert isinstance(directive, CanonicalDirective)

    step_engine = Engine()
    step_engine.import_json(json.dumps(initial_state, sort_keys=True, separators=(",", ":")))
    step_decision = step_engine.step(text)
    step_state = _observations(step_engine)

    apply_engine = Engine()
    apply_engine.import_json(json.dumps(initial_state, sort_keys=True, separators=(",", ":")))
    apply_decision = apply_engine.apply_directive(directive)
    apply_state = _observations(apply_engine)

    assert step_decision == apply_decision
    assert step_state == apply_state


@given(GRAMMAR_RENDER_CASES)
def test_grammar_helper_render_decompose_round_trip_is_stable(
    case: dict[str, DirectiveKind | dict[str, str]],
) -> None:
    kind = case["kind"]
    operands = case["operands"]

    assert isinstance(kind, DirectiveKind)
    assert isinstance(operands, dict)

    rendered = grammar_module._render_directive(kind, **operands)
    directive = decompose_directive(rendered)

    assert isinstance(directive, CanonicalDirective)
    assert directive.kind is kind
    assert directive.text == rendered
    assert dict(directive.operands) == operands
    assert decompose_directive(directive.text) == directive
    assert grammar_module._render_directive(kind, **operands) == rendered


@given(st.sampled_from(get_directive_metadata()))
def test_public_directive_metadata_matches_internal_rendering_contract(
    metadata: grammar_module.DirectiveMetadata,
) -> None:
    spec = grammar_module._DIRECTIVE_SPECS[metadata.kind]

    assert metadata.canonical_start == spec.canonical_start
    assert metadata.operand_names == spec.operand_names

    if metadata.kind is DirectiveKind.SET_PREMISE:
        rendered = grammar_module._render_directive(metadata.kind, value="concise replies")
    elif metadata.kind is DirectiveKind.CHANGE_PREMISE:
        rendered = grammar_module._render_directive(metadata.kind, value="formal tone")
    elif metadata.kind is DirectiveKind.USE_ITEM:
        rendered = grammar_module._render_directive(metadata.kind, item="docker")
    elif metadata.kind is DirectiveKind.PROHIBIT_ITEM:
        rendered = grammar_module._render_directive(metadata.kind, item="peanuts")
    elif metadata.kind is DirectiveKind.REMOVE_POLICY:
        rendered = grammar_module._render_directive(metadata.kind, item="docker")
    elif metadata.kind is DirectiveKind.REPLACE_USE:
        rendered = grammar_module._render_directive(
            metadata.kind,
            new_item="podman",
            old_item="docker",
        )
    elif (
        metadata.kind is DirectiveKind.CLEAR_PREMISE
        or metadata.kind is DirectiveKind.RESET_POLICIES
    ):
        rendered = grammar_module._render_directive(metadata.kind)
    else:
        assert metadata.kind is DirectiveKind.CLEAR_STATE
        rendered = grammar_module._render_directive(metadata.kind)

    directive = decompose_directive(rendered)
    assert isinstance(directive, CanonicalDirective)
    assert directive.kind is metadata.kind
    assert tuple(directive.operands) == metadata.operand_names
    assert _normalize_item_like_engine(rendered.split()[0]) == _normalize_item_like_engine(
        metadata.canonical_start.split()[0]
    )


def test_public_directive_metadata_only_collides_on_canonical_start_for_use_families() -> None:
    starts_by_kind = {
        metadata.kind: metadata.canonical_start for metadata in get_directive_metadata()
    }

    assert starts_by_kind[DirectiveKind.USE_ITEM] == starts_by_kind[DirectiveKind.REPLACE_USE]

    inverse: dict[str, set[DirectiveKind]] = {}
    for kind, start in starts_by_kind.items():
        inverse.setdefault(start, set()).add(kind)

    assert inverse["use"] == {DirectiveKind.USE_ITEM, DirectiveKind.REPLACE_USE}
    for start, kinds in inverse.items():
        if start != "use":
            assert len(kinds) == 1, start


@given(st.text(min_size=1, max_size=30))
def test_idempotent_use_item_is_update_and_stable_state(item: str) -> None:
    assume(" instead of " not in item)
    assume(not item.startswith("instead of "))
    assume(not item.endswith(" instead of"))
    assume(_normalize_item_like_engine(item) != "")
    assume(not _contains_canonical_start_fragment(item))
    assume(_is_canonical_directive(decompose_directive(f"use {item}")))
    engine = Engine()
    d1 = engine.step(f"use {item}")
    d2 = engine.step(f"use {item}")

    assert d1["kind"] == "update"
    assert d2["kind"] == "update"
    assert len(engine.policies) == 1


@given(item=st.text(alphabet=" \t", min_size=0, max_size=6))
def test_use_item_with_whitespace_only_payload_remains_no_directive(item: str) -> None:
    assert _normalize_item_like_engine(item) == ""
    engine = Engine()
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
    assume(_is_canonical_directive(decompose_directive(f"prohibit {item}")))
    engine = Engine()
    d1 = engine.step(f"prohibit {item}")
    d2 = engine.step(f"prohibit {item}")

    assert d1["kind"] == DECISION_UPDATE
    assert d2["kind"] == DECISION_UPDATE
    assert len(engine.policies) == 1


@given(item=st.text(alphabet=" \t", min_size=0, max_size=6))
def test_prohibit_item_with_whitespace_only_payload_remains_no_directive(item: str) -> None:
    assert _normalize_item_like_engine(item) == ""
    engine = Engine()
    before = _observations(engine)

    d1 = engine.step(f"prohibit {item}")
    d2 = engine.step(f"prohibit {item}")

    assert d1 == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert d2 == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


@given(st.lists(st.text(max_size=80), min_size=0, max_size=20))
def test_non_matching_inputs_can_remain_no_directive_only(inputs: list[str]) -> None:
    engine = Engine()
    before = _observations(engine)

    for text in inputs:
        decision = engine.step(f"please {text}")
        assert decision["kind"] == DECISION_NO_DIRECTIVE

    assert _observations(engine) == before


@given(st.lists(st.text(max_size=50), min_size=0, max_size=30))
def test_no_directive_sequence_preserves_state_and_decision_kind(inputs: list[str]) -> None:
    engine = Engine()
    before = _observations(engine)

    for text in inputs:
        decision = engine.step(f"prefix {text}")
        assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
        assert _observations(engine) == before


@given(st.text(min_size=1, max_size=30))
def test_contradiction_use_after_prohibit_always_clarifies(item: str) -> None:
    assume(not _contains_canonical_start_fragment(item))
    assume(_is_canonical_directive(decompose_directive(f"prohibit {item}")))
    assume(_is_canonical_directive(decompose_directive(f"use {item}")))
    engine = Engine()
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
    assume(_is_canonical_directive(decompose_directive(f"use {item}")))
    assume(_is_canonical_directive(decompose_directive(f"prohibit {item}")))
    engine = Engine()
    engine.step(f"use {item}")
    before = _observations(engine)

    decision = engine.step(f"prohibit {item}")
    assert decision["kind"] == DECISION_ERROR
    assert _observations(engine) == before


@given(VALID_STATE_PAYLOADS)
def test_export_import_round_trip_preserves_authoritative_state_for_generated_payloads(
    payload: dict[str, object],
) -> None:
    source = Engine()
    source.import_json(json.dumps(payload))
    canonical_state = _observations(source)

    target = Engine()
    target.import_json(source.export_json())

    assert _observations(target) == canonical_state


@given(VALID_STATE_PAYLOADS, st.integers(min_value=1, max_value=5))
def test_repeated_export_import_cycles_remain_stable(
    payload: dict[str, object], cycles: int
) -> None:
    engine = Engine()
    engine.import_json(json.dumps(payload))

    expected_state = _observations(engine)
    expected_json = engine.export_json()

    for _ in range(cycles):
        next_engine = Engine()
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

    assert isinstance(initial_state, dict)
    assert isinstance(new_item, str)
    assert isinstance(old_item, str)

    oracle_engine = Engine()
    oracle_engine.import_json(
        json.dumps(deepcopy(initial_state), sort_keys=True, separators=(",", ":"))
    )
    oracle_engine.step(f"remove policy {old_item}")
    expected_decision = oracle_engine.step(f"use {new_item}")
    expected_state = _observations(oracle_engine)

    engine = Engine()
    engine.import_json(json.dumps(initial_state, sort_keys=True, separators=(",", ":")))
    decision = engine.step(f"use {new_item} instead of {old_item}")

    assert expected_decision == {
        "kind": DECISION_UPDATE,
        "message": None,
    }
    assert decision == expected_decision
    assert _observations(engine) == expected_state


@given(ERROR_CASES)
def test_apply_directive_semantic_errors_never_partially_mutate_state(
    case: tuple[dict[str, object], CanonicalDirective],
) -> None:
    initial_state, directive = case
    engine = Engine()
    engine.import_json(json.dumps(initial_state, sort_keys=True, separators=(",", ":")))
    before = _observations(engine)

    decision = engine.apply_directive(directive)

    assert decision == {"kind": DECISION_ERROR, "message": decision["message"]}
    assert decision["message"] is not None
    assert _observations(engine) == before


@given(REPLACEMENT_ERROR_CASES)
def test_apply_directive_replacement_error_cases_preserve_state(
    case: tuple[dict[str, object], str, str, str],
) -> None:
    initial_state, new_item, old_item, _reason = case
    engine = Engine()
    engine.import_json(json.dumps(initial_state, sort_keys=True, separators=(",", ":")))
    directive = _canonical_directive_from_text(f"use {new_item} instead of {old_item}")
    before = _observations(engine)

    decision = engine.apply_directive(directive)

    assert decision["kind"] == DECISION_ERROR
    assert decision["message"] is not None
    assert _observations(engine) == before


@given(CANONICAL_GRAMMAR_ITEM_TEXT)
def test_apply_directive_replacement_with_normalized_equivalent_keys_is_noop_update(
    item: str,
) -> None:
    original_normalized = _normalize_item_like_engine(item)
    upper_normalized = _normalize_item_like_engine(item.upper())
    assume(original_normalized != "")
    assume(original_normalized == upper_normalized)
    normalized = original_normalized
    engine = Engine()
    engine.import_json(
        json.dumps(
            {"premise": None, "policies": {normalized: "use"}, "version": 2},
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    before = _observations(engine)
    directive = _canonical_directive_from_text(f"use {item.upper()} instead of {item}")

    decision = engine.apply_directive(directive)

    assert decision == {"kind": DECISION_UPDATE, "message": None}
    assert _observations(engine) == before


@given(DETERMINISTIC_REPLACEMENT_CASES)
def test_apply_directive_valid_replacement_performs_expected_transition(
    case: dict[str, object],
) -> None:
    initial_state = case["initial_state"]
    new_item = case["new_item"]
    old_item = case["old_item"]

    assert isinstance(initial_state, dict)
    assert isinstance(new_item, str)
    assert isinstance(old_item, str)

    engine = Engine()
    engine.import_json(json.dumps(initial_state, sort_keys=True, separators=(",", ":")))
    directive = _canonical_directive_from_text(f"use {new_item} instead of {old_item}")
    before_premise, before_policies = _observations(engine)

    decision = engine.apply_directive(directive)

    expected_policies = dict(before_policies)
    expected_policies.pop(_normalize_item_like_engine(old_item), None)
    expected_policies[_normalize_item_like_engine(new_item)] = "use"

    assert decision == {"kind": DECISION_UPDATE, "message": None}
    assert _observations(engine) == (before_premise, expected_policies)


@given(st.lists(POLICY_MACHINE_OPERATIONS, min_size=1, max_size=25))
def test_apply_directive_policy_lifecycle_matches_simple_state_model(
    operations: list[tuple[str, ...]],
) -> None:
    engine = Engine()
    model: dict[str, str] = {}

    for operation in operations:
        before = _observations(engine)
        before_model = dict(model)

        if operation[0] == "use":
            item = operation[1]
            directive = _canonical_directive_from_text(f"use {item}")
            key = _normalize_item_like_engine(item)
            expected_error = model.get(key) == "prohibit"
            if not expected_error:
                model[key] = "use"
        elif operation[0] == "prohibit":
            item = operation[1]
            directive = _canonical_directive_from_text(f"prohibit {item}")
            key = _normalize_item_like_engine(item)
            expected_error = model.get(key) == "use"
            if not expected_error:
                model[key] = "prohibit"
        elif operation[0] == "remove":
            item = operation[1]
            directive = _canonical_directive_from_text(f"remove policy {item}")
            key = _normalize_item_like_engine(item)
            expected_error = False
            model.pop(key, None)
        else:
            assert operation[0] == "replace"
            new_item = operation[1]
            old_item = operation[2]
            directive = _canonical_directive_from_text(f"use {new_item} instead of {old_item}")
            new_key = _normalize_item_like_engine(new_item)
            old_key = _normalize_item_like_engine(old_item)
            if new_key == old_key:
                expected_error = False
            else:
                expected_error = model.get(old_key) != "use" or model.get(new_key) == "prohibit"
                if not expected_error:
                    model.pop(old_key, None)
                    model[new_key] = "use"

        decision = engine.apply_directive(directive)

        if expected_error:
            assert decision["kind"] == DECISION_ERROR
            assert _observations(engine) == before
            assert model == before_model
        else:
            assert decision == {"kind": DECISION_UPDATE, "message": None}
            assert dict(engine.policies) == model
            assert all(value in {"use", "prohibit"} for value in model.values())


@given(st.lists(PREMISE_MACHINE_OPERATIONS, min_size=1, max_size=25))
def test_apply_directive_premise_lifecycle_matches_simple_model(
    operations: list[tuple[str, ...]],
) -> None:
    engine = Engine()
    model_premise: str | None = None

    for operation in operations:
        before_premise, before_policies = _observations(engine)
        before_model_premise = model_premise

        if operation[0] == "set":
            value = operation[1]
            directive = _canonical_directive_from_text(f"set premise {value}")
            expected_error = model_premise is not None
            if not expected_error:
                model_premise = _sanitize_premise_like_engine(value)
        elif operation[0] == "change":
            value = operation[1]
            directive = _canonical_directive_from_text(f"change premise to {value}")
            expected_error = model_premise is None
            if not expected_error:
                model_premise = _sanitize_premise_like_engine(value)
        elif operation[0] == "clear_premise":
            directive = _canonical_directive_from_text("clear premise")
            expected_error = False
            model_premise = None
        else:
            assert operation[0] == "clear_state"
            directive = _canonical_directive_from_text("clear state")
            expected_error = False
            model_premise = None

        decision = engine.apply_directive(directive)
        after_premise, after_policies = _observations(engine)

        if expected_error:
            assert decision["kind"] == DECISION_ERROR
            assert after_premise == before_premise
            assert after_policies == before_policies
            assert model_premise == before_model_premise
        else:
            assert decision == {"kind": DECISION_UPDATE, "message": None}
            assert after_premise == model_premise
            if operation[0] == "clear_state":
                assert after_policies == {}
            else:
                assert after_policies == before_policies


@given(EQUIVALENT_NORMALIZED_KEY_PAIRS)
def test_import_json_normalization_converges_equivalent_policy_keys(
    pair: tuple[str, str],
) -> None:
    raw_a, raw_b = pair

    payload = {
        "premise": None,
        "policies": {raw_a: "use", raw_b: "prohibit"},
        "version": 2,
    }
    engine = Engine()
    engine.import_json(json.dumps(payload, sort_keys=True, separators=(",", ":")))

    normalized_key = _normalize_item_like_engine(raw_b)
    expected_value = {
        _normalize_item_like_engine(raw_key): value
        for raw_key, value in sorted(payload["policies"].items())
    }[normalized_key]
    assert _observations(engine) == (None, {normalized_key: expected_value})


@given(INVALID_EMPTY_NORMALIZED_KEY_TEXT)
def test_import_json_rejects_policy_keys_that_normalize_to_empty(key: str) -> None:
    engine = Engine()
    before = _observations(engine)
    payload = {"premise": None, "policies": {key: "use"}, "version": 2}

    try:
        engine.import_json(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    except ValueError as exc:
        assert str(exc) == "Invalid state payload."
    else:
        raise AssertionError("Expected ValueError for empty normalized policy key")

    assert _observations(engine) == before


@given(VALID_STATE_PAYLOADS)
def test_import_json_preserves_authoritative_invariants_for_generated_payloads(
    payload: dict[str, object],
) -> None:
    engine = Engine()
    engine.import_json(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    premise, policies = _observations(engine)

    assert premise is None or premise == _sanitize_premise_like_engine(premise)
    assert all(key == _normalize_item_like_engine(key) for key in policies)
    assert all(value in {"use", "prohibit"} for value in policies.values())


@given(REPLACEMENT_NEAR_MISS_CASES)
def test_replacement_near_misses_never_parse_as_canonical_or_mutate_state(text: str) -> None:
    engine = Engine()
    before = _observations(engine)
    parsed = decompose_directive(text)
    decision = engine.step(text)

    assert not (isinstance(parsed, CanonicalDirective) and parsed.kind is DirectiveKind.REPLACE_USE)
    assert decision == {"kind": DECISION_NO_DIRECTIVE, "message": None}
    assert _observations(engine) == before


@given(
    st.one_of(
        VALID_NONEMPTY_ITEM_TEXT.map(lambda old_item: (f"use instead of {old_item}", "new_item")),
        VALID_USE_ITEM_TEXT.map(lambda new_item: (f"use {new_item} instead of", "old_item")),
    )
)
def test_incomplete_replacement_forms_report_replace_use_family(
    case: tuple[str, str],
) -> None:
    text, missing_operand = case
    parsed = decompose_directive(text)

    assert isinstance(parsed, InvalidDirectiveSyntax)
    assert parsed.failure is DirectiveSyntaxFailure.MISSING_REQUIRED_OPERAND
    assert parsed.missing_operand == missing_operand
    assert parsed.directive_kind in {DirectiveKind.REPLACE_USE, DirectiveKind.USE_ITEM}
