import json
import re
from unicodedata import normalize as unicode_normalize

from hypothesis import assume, given
from hypothesis import strategies as st

from context_compiler import create_engine
from context_compiler.engine import _CANONICAL_DIRECTIVE_STARTS, State
from context_compiler.grammar import validate_directive


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


def _canonicalize_state_payload(payload: dict[str, object]) -> State:
    premise = payload["premise"]
    assert premise is None or isinstance(premise, str)

    raw_policies = payload["policies"]
    assert isinstance(raw_policies, dict)

    normalized_policies = {
        _normalize_item_like_engine(key): value
        for key, value in raw_policies.items()
        if isinstance(key, str)
    }

    return {
        "premise": None if premise is None else _sanitize_premise_like_engine(premise),
        "policies": dict(sorted(normalized_policies.items())),
        "version": 2,
    }


@given(st.lists(st.text(max_size=40), min_size=0, max_size=20))
def test_determinism_same_input_sequence_same_state(inputs: list[str]) -> None:
    assert _run_sequence(inputs) == _run_sequence(inputs)


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


@given(VALID_STATE_PAYLOADS)
def test_generated_valid_states_canonicalize_deterministically(
    payload: dict[str, object],
) -> None:
    expected_state = _canonicalize_state_payload(payload)

    engine1 = create_engine()
    engine1.import_json(json.dumps(payload))

    engine2 = create_engine()
    engine2.import_json(json.dumps(payload))

    assert engine1.state == expected_state
    assert engine2.state == expected_state
    assert engine1.export_json() == engine2.export_json()
