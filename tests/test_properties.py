import json
import re
from copy import deepcopy
from unicodedata import normalize as unicode_normalize

from hypothesis import assume, given
from hypothesis import strategies as st

from context_compiler import create_engine
from context_compiler.controller import preview, state_diff
from context_compiler.engine import _CANONICAL_DIRECTIVE_STARTS, State
from context_compiler.grammar import DirectiveKind, render_directive, validate_directive


def _run_sequence(inputs: list[str]) -> State:
    engine = create_engine()
    for item in inputs:
        engine.step(item)
    return engine.state


def _normalize_item_like_engine(value: str) -> str:
    normalized = unicode_normalize("NFKC", value)
    normalized = normalized.replace("’", "'").replace("`", "'")
    normalized = normalized.lower()
    normalized = re.sub(r"\bdont\b", "don't", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"^(?:a|an|the)\b\s*", "", normalized)
    return normalized.strip()


def _contains_canonical_start_fragment(value: str) -> bool:
    for start in range(len(value)):
        if start > 0 and value[start - 1].isalpha():
            continue
        for token, require_space_or_end in _CANONICAL_DIRECTIVE_STARTS:
            if not value.startswith(token, start):
                continue
            end = start + len(token)
            if end == len(value):
                return True
            next_char = value[end]
            if require_space_or_end:
                if next_char == " ":
                    return True
            elif not next_char.isalpha():
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
).filter(lambda payload: all(_normalize_item_like_engine(key) != "" for key in payload["policies"]))


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
    lambda value: validate_directive(f"use {value}") is not None
)

VALID_PROHIBIT_ITEM_TEXT = VALID_NONEMPTY_ITEM_TEXT.filter(
    lambda value: validate_directive(f"prohibit {value}") is not None
)

VALID_PREMISE_TEXT = NORMALIZATION_SENSITIVE_TEXT.filter(
    lambda value: _sanitize_premise_like_engine(value) != ""
)

CANONICAL_GRAMMAR_PREMISE_TEXT = NORMALIZATION_SENSITIVE_TEXT.map(
    _sanitize_premise_like_engine
).filter(
    lambda value: (
        value != ""
        and validate_directive(f"set premise {value}") is not None
        and validate_directive(f"change premise to {value}") is not None
    )
)

CANONICAL_GRAMMAR_ITEM_TEXT = NORMALIZATION_SENSITIVE_TEXT.map(_normalize_item_like_engine).filter(
    lambda value: (
        value != ""
        and validate_directive(f"use {value}") is not None
        and validate_directive(f"prohibit {value}") is not None
        and validate_directive(f"remove policy {value}") is not None
    )
)

PREVIEW_INPUTS = st.one_of(
    st.text(max_size=40),
    VALID_USE_ITEM_TEXT.map(lambda item: f"use {item}"),
    VALID_PROHIBIT_ITEM_TEXT.map(lambda item: f"prohibit {item}"),
    VALID_NONEMPTY_ITEM_TEXT.map(lambda item: f"remove policy {item}").filter(
        lambda text: validate_directive(text) is not None
    ),
    VALID_PREMISE_TEXT.map(lambda value: f"set premise {value}").filter(
        lambda text: validate_directive(text) is not None
    ),
    VALID_PREMISE_TEXT.map(lambda value: f"change premise to {value}").filter(
        lambda text: validate_directive(text) is not None
    ),
    st.sampled_from(["clear premise", "reset policies", "clear state"]),
    st.tuples(VALID_USE_ITEM_TEXT, VALID_NONEMPTY_ITEM_TEXT)
    .filter(
        lambda pair: _normalize_item_like_engine(pair[0]) != _normalize_item_like_engine(pair[1])
    )
    .map(lambda pair: f"use {pair[0]} instead of {pair[1]}")
    .filter(lambda text: validate_directive(text) is not None),
)

DETERMINISTIC_REPLACEMENT_CASES = st.builds(
    lambda payload, new_item, old_item, old_present: {
        "payload": payload,
        "new_item": new_item,
        "old_item": old_item,
        "old_present": old_present,
    },
    payload=VALID_STATE_PAYLOADS,
    new_item=VALID_USE_ITEM_TEXT,
    old_item=VALID_NONEMPTY_ITEM_TEXT,
    old_present=st.booleans(),
).filter(
    lambda case: (
        _normalize_item_like_engine(case["new_item"])
        != _normalize_item_like_engine(case["old_item"])
        and validate_directive(f"use {case['new_item']} instead of {case['old_item']}") is not None
    )
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

    return restored.state == engine.state


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
    validated = validate_directive(rendered)

    assert validated is not None
    assert validated.kind is kind
    assert validated.text == rendered
    assert validate_directive(validated.text) == validated
    assert render_directive(kind, **operands) == rendered


@given(st.text(min_size=1, max_size=30))
def test_idempotent_use_item_is_update_and_stable_state(item: str) -> None:
    assume(" instead of " not in item)
    assume(not item.startswith("instead of "))
    assume(not item.endswith(" instead of"))
    assume(_normalize_item_like_engine(item) != "")
    assume(not _contains_canonical_start_fragment(item))
    assume(validate_directive(f"use {item}") is not None)
    engine = create_engine()
    d1 = engine.step(f"use {item}")
    d2 = engine.step(f"use {item}")

    assert d1["kind"] == "update"
    assert d2["kind"] == "update"
    assert len(engine.state["policies"]) == 1


@given(
    article=st.sampled_from(["a", "an", "the", "A", "An", "The", "THE"]),
    leading_ws=st.text(alphabet=" \t", min_size=0, max_size=3),
    trailing_ws=st.text(alphabet=" \t", min_size=0, max_size=3),
)
def test_use_item_with_empty_normalized_payload_clarifies_without_mutation(
    article: str, leading_ws: str, trailing_ws: str
) -> None:
    item = f"{leading_ws}{article}{trailing_ws}"
    assert _normalize_item_like_engine(item) == ""
    engine = create_engine()
    before = engine.state

    d1 = engine.step(f"use {item}")
    d2 = engine.step(f"use {item}")

    expected_prompt = "Policy item cannot be empty.\nUse 'use <item>' with a non-empty value."
    assert d1 == {"kind": "clarify", "state": None, "prompt_to_user": expected_prompt}
    assert d2 == {"kind": "clarify", "state": None, "prompt_to_user": expected_prompt}
    assert engine.state == before


@given(st.text(min_size=1, max_size=30))
def test_idempotent_prohibit_item_is_update_and_stable_state(item: str) -> None:
    assume(_normalize_item_like_engine(item) != "")
    assume(not _contains_canonical_start_fragment(item))
    assume(validate_directive(f"prohibit {item}") is not None)
    engine = create_engine()
    d1 = engine.step(f"prohibit {item}")
    d2 = engine.step(f"prohibit {item}")

    assert d1["kind"] == "update"
    assert d2["kind"] == "update"
    assert len(engine.state["policies"]) == 1


@given(
    article=st.sampled_from(["a", "an", "the", "A", "An", "The", "THE"]),
    leading_ws=st.text(alphabet=" \t", min_size=0, max_size=3),
    trailing_ws=st.text(alphabet=" \t", min_size=0, max_size=3),
)
def test_prohibit_item_with_empty_normalized_payload_clarifies_without_mutation(
    article: str, leading_ws: str, trailing_ws: str
) -> None:
    item = f"{leading_ws}{article}{trailing_ws}"
    assert _normalize_item_like_engine(item) == ""
    engine = create_engine()
    before = engine.state

    d1 = engine.step(f"prohibit {item}")
    d2 = engine.step(f"prohibit {item}")

    expected_prompt = "Policy item cannot be empty.\nUse 'prohibit <item>' with a non-empty value."
    assert d1 == {"kind": "clarify", "state": None, "prompt_to_user": expected_prompt}
    assert d2 == {"kind": "clarify", "state": None, "prompt_to_user": expected_prompt}
    assert engine.state == before


@given(st.lists(st.text(max_size=80), min_size=0, max_size=20))
def test_non_matching_inputs_can_remain_passthrough_only(inputs: list[str]) -> None:
    engine = create_engine()
    before = engine.state

    for text in inputs:
        decision = engine.step(f"please {text}")
        assert decision["kind"] == "passthrough"

    assert engine.state == before


@given(st.lists(st.text(max_size=50), min_size=0, max_size=30))
def test_passthrough_sequence_preserves_state_and_decision_kind(inputs: list[str]) -> None:
    engine = create_engine()
    before = engine.state

    for text in inputs:
        decision = engine.step(f"prefix {text}")
        assert decision == {"kind": "passthrough", "state": None, "prompt_to_user": None}
        assert engine.state == before


@given(st.text(min_size=1, max_size=30))
def test_contradiction_use_after_prohibit_always_clarifies(item: str) -> None:
    assume(not _contains_canonical_start_fragment(item))
    assume(validate_directive(f"prohibit {item}") is not None)
    assume(validate_directive(f"use {item}") is not None)
    engine = create_engine()
    engine.step(f"prohibit {item}")
    before = engine.state

    decision = engine.step(f"use {item}")
    assert decision["kind"] == "clarify"
    assert engine.state == before


@given(st.text(min_size=1, max_size=30))
def test_contradiction_prohibit_after_use_always_clarifies(item: str) -> None:
    assume(" instead of " not in item)
    assume(not item.startswith("instead of "))
    assume(not item.endswith(" instead of"))
    assume(not _contains_canonical_start_fragment(item))
    assume(validate_directive(f"use {item}") is not None)
    assume(validate_directive(f"prohibit {item}") is not None)
    engine = create_engine()
    engine.step(f"use {item}")
    before = engine.state

    decision = engine.step(f"prohibit {item}")
    assert decision["kind"] == "clarify"
    assert engine.state == before


@given(VALID_STATE_PAYLOADS)
def test_export_import_round_trip_preserves_authoritative_state_for_generated_payloads(
    payload: dict[str, object],
) -> None:
    source = create_engine()
    source.import_json(json.dumps(payload))
    canonical_state = source.state

    target = create_engine()
    target.import_json(source.export_json())

    assert target.state == canonical_state


@given(VALID_STATE_PAYLOADS, st.integers(min_value=1, max_value=5))
def test_repeated_export_import_cycles_remain_stable(
    payload: dict[str, object], cycles: int
) -> None:
    engine = create_engine()
    engine.import_json(json.dumps(payload))

    expected_state = engine.state
    expected_json = engine.export_json()

    for _ in range(cycles):
        next_engine = create_engine()
        next_engine.import_json(expected_json)
        assert next_engine.state == expected_state
        assert next_engine.export_json() == expected_json
        expected_state = next_engine.state
        expected_json = next_engine.export_json()


@given(DETERMINISTIC_REPLACEMENT_CASES)
def test_deterministic_replacement_matches_equivalent_explicit_transition(
    case: dict[str, object],
) -> None:
    payload = case["payload"]
    new_item = case["new_item"]
    old_item = case["old_item"]
    old_present = case["old_present"]

    assert isinstance(payload, dict)
    assert isinstance(new_item, str)
    assert isinstance(old_item, str)
    assert isinstance(old_present, bool)

    initial_state_engine = create_engine()
    initial_state_engine.import_json(json.dumps(payload))
    initial_state = initial_state_engine.state
    new_key = _normalize_item_like_engine(new_item)
    old_key = _normalize_item_like_engine(old_item)

    policies = dict(initial_state["policies"])
    policies.pop(new_key, None)
    if old_present:
        policies[old_key] = "use"
    else:
        policies.pop(old_key, None)

    initial_state = {
        "premise": initial_state["premise"],
        "policies": dict(sorted(policies.items())),
        "version": 2,
    }
    assume(initial_state["policies"].get(new_key) != "prohibit")
    assume(initial_state["policies"].get(old_key) != "prohibit")

    oracle_engine = create_engine(state=deepcopy(initial_state))
    oracle_engine.step(f"remove policy {old_item}")
    expected_decision = oracle_engine.step(f"use {new_item}")
    expected_state = oracle_engine.state

    engine = create_engine(state=initial_state)
    decision = engine.step(f"use {new_item} instead of {old_item}")

    assert expected_decision == {"kind": "update", "state": expected_state, "prompt_to_user": None}
    assert decision == expected_decision
    assert engine.state == expected_state
    assert engine.has_pending_clarification() is False

    if not old_present:
        followup = engine.step("yes")
        assert followup == {"kind": "passthrough", "state": None, "prompt_to_user": None}
        assert engine.has_pending_clarification() is False
        assert engine.state == expected_state


@given(VALID_STATE_PAYLOADS.filter(_payload_has_stable_export_import_cycle), PREVIEW_INPUTS)
def test_preview_matches_isolated_execution_without_mutating_live_engine(
    payload: dict[str, object], user_input: str
) -> None:
    live_engine = create_engine()
    live_engine.import_json(json.dumps(payload))
    before = deepcopy(live_engine.state)

    preview_result = preview(live_engine, user_input)

    isolated_engine = create_engine()
    isolated_engine.import_json(json.dumps(before))
    isolated_decision = isolated_engine.step(user_input)
    isolated_after = isolated_engine.state
    isolated_diff = state_diff(before, isolated_after)

    assert live_engine.state == before
    assert preview_result["decision"] == isolated_decision
    assert preview_result["state_before"] == before
    assert preview_result["state_after"] == isolated_after
    assert preview_result["diff"] == isolated_diff
    assert preview_result["would_mutate"] is (before != isolated_after)
    assert preview_result["would_mutate"] is preview_result["diff"]["changed"]
