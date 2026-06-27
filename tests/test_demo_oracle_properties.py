import importlib.util
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_demo_module(filename: str):
    module_path = REPO_ROOT / "demos" / filename
    spec = importlib.util.spec_from_file_location(f"oracle_props_{filename}", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DEMO02 = _load_demo_module("02_llm_constraint_guardrail.py")
DEMO03 = _load_demo_module("03_llm_premise_guardrail.py")
DEMO04 = _load_demo_module("04_llm_tool_denylist_guardrail.py")
DEMO05 = _load_demo_module("05_llm_prompt_drift_vs_state.py")
DEMO07 = _load_demo_module("07_llm_prompt_vs_state.py")
COMMON = _load_demo_module("common.py")


@given(
    pre=st.sampled_from(["", " ", "  ", "\t"]),
    post=st.sampled_from(["", " ", "  ", "\t"]),
    punct=st.sampled_from(["", ".", "!", "?"]),
)
def test_demo02_prohibited_detection_flags_plain_peanut_mentions(
    pre: str, post: str, punct: str
) -> None:
    output = f"Ingredients:\n- {pre}peanuts{post}{punct}\nSteps:\n1. Cook."
    assert DEMO02.recipe_includes_prohibited_item(output)


@given(
    line=st.sampled_from(
        [
            "Ingredients: peanut-free sauce",
            "Ingredients: without peanuts",
            "Ingredients: no peanuts",
            "Ingredients: free of peanuts",
            "I cannot provide peanuts due to policy.",
            "Cashew Curry uses cashews instead of peanuts.",
            "Creamy Cashew Curry (using cashews rather than peanuts).",
            "Sunflower Seed Curry in place of peanuts.",
            "Sunflower Seed Peanut-Style Curry",
            "Sunflower Seed Peanut Like Curry",
            "Sunflower Seed Peanut-like Curry",
        ]
    )
)
def test_demo02_prohibited_detection_ignores_safe_or_refusal_phrasing(line: str) -> None:
    assert not DEMO02.recipe_includes_prohibited_item(line)


@given(
    line=st.sampled_from(
        [
            "Here is a recipe that exclude peanuts.",
            "Here is a recipe that excludes peanuts.",
            "Here is a recipe excluding peanuts.",
            "Here is a recipe with no peanuts.",
            "Here is a recipe without peanuts.",
            "Here is a peanut-free recipe.",
            "Here is a recipe that avoids peanuts.",
        ]
    )
)
def test_demo02_prohibited_detection_ignores_negated_policy_mentions(line: str) -> None:
    assert not DEMO02.recipe_includes_prohibited_item(line)


@given(
    line=st.sampled_from(
        [
            "I cannot provide that recipe; it conflicts with policy.",
            "I can't provide peanuts.",
            "I must decline this request because it is prohibited.",
            "This is not allowed by policy.",
        ]
    )
)
def test_demo02_refusal_detected_is_case_insensitive(line: str) -> None:
    assert DEMO02.refusal_detected(line.upper())


@given(
    line=st.sampled_from(
        [
            "Try a peanut-free curry alternative.",
            "Use chickpeas instead.",
            "Here is a safe alternative recipe.",
        ]
    )
)
def test_demo02_safe_alternative_detected(line: str) -> None:
    assert DEMO02.safe_alternative_detected(line)


@given(
    line=st.sampled_from(
        [
            "Use a vegan or vegetarian curry paste.",
            "Use vegan/vegetarian stock cubes.",
            "A vegan and vegetarian option works.",
        ]
    )
)
def test_demo03_stale_value_checker_ignores_lines_with_current_and_stale_terms(line: str) -> None:
    output = f"Shopping list:\n- tofu\n- spinach\n{line}"
    assert not DEMO03._plan_uses_value(output, "vegetarian")


@given(
    line=st.sampled_from(
        [
            "Use vegetarian stock.",
            "Vegetarian curry paste is fine.",
            "This plan is vegetarian.",
        ]
    )
)
def test_demo03_stale_value_checker_flags_unnegated_stale_term(line: str) -> None:
    output = f"Plan:\n- tofu\n{line}"
    assert DEMO03._plan_uses_value(output, "vegetarian")


@given(
    line=st.sampled_from(
        [
            "without vegetarian stock",
            "avoid vegetarian items",
            "no vegetarian ingredients",
            "exclude vegetarian products",
        ]
    )
)
def test_demo03_stale_value_checker_ignores_negated_stale_term(line: str) -> None:
    output = f"Plan:\n- tofu\n{line}"
    assert not DEMO03._plan_uses_value(output, "vegetarian")


@given(
    line=st.sampled_from(
        [
            "excluding vegetarian products",
            "excludes vegetarian products",
            "avoids vegetarian products",
            "vegetarian-free option only",
        ]
    )
)
def test_demo03_stale_value_checker_ignores_inflected_negation(line: str) -> None:
    output = f"Plan:\n- tofu\n{line}"
    assert not DEMO03._plan_uses_value(output, "vegetarian")


@given(
    tag=st.sampled_from(["vegetarian curry", "Vegetarian Curry", " VEGETARIAN CURRY "]),
    punct=st.sampled_from(["", ".", "!", "?", "?!"]),
)
def test_demo05_premise_match_accepts_case_whitespace_and_trailing_punctuation(
    tag: str, punct: str
) -> None:
    output = f"PREMISE: {tag}{punct}\nDinner Plan:\n- tofu"
    assert DEMO05.premise_matches_expected(output)


@given(
    quote=st.sampled_from(['"', "'", "“", "”"]),
    punct=st.sampled_from(["", ".", "!", "?"]),
)
def test_demo05_premise_match_accepts_wrapped_quotes(quote: str, punct: str) -> None:
    output = f"PREMISE: {quote}vegetarian curry{quote}{punct}\nDinner Plan:\n- tofu"
    assert DEMO05.premise_matches_expected(output)


@given(wrong=st.sampled_from(["vegan curry", "chicken curry", "curry", "vegetarian stew"]))
def test_demo05_premise_match_rejects_wrong_semantic_values(wrong: str) -> None:
    output = f"PREMISE: {wrong}\nDinner Plan:\n- tofu"
    assert not DEMO05.premise_matches_expected(output)


@given(
    line=st.sampled_from(
        [
            "Dinner plan: chicken curry",
            "- beef stew",
            "- shrimp fried rice",
        ]
    )
)
def test_demo05_non_veg_detection_flags_unnegated_non_veg(line: str) -> None:
    output = f"PREMISE: vegetarian curry\n{line}"
    assert DEMO05.plan_includes_non_vegetarian_item(output)


@given(
    line=st.sampled_from(
        [
            "Dinner plan: without chicken",
            "- avoid beef",
            "- no shrimp",
            "- exclude pork",
        ]
    )
)
def test_demo05_non_veg_detection_ignores_negated_non_veg(line: str) -> None:
    output = f"PREMISE: vegetarian curry\n{line}"
    assert not DEMO05.plan_includes_non_vegetarian_item(output)


@given(
    line=st.sampled_from(
        [
            "- excludes chicken",
            "- excluding beef",
            "- avoids pork",
            "- chicken-free broth",
        ]
    )
)
def test_demo05_non_veg_detection_ignores_inflected_or_freeform_negation(line: str) -> None:
    output = f"PREMISE: vegetarian curry\n{line}"
    assert not DEMO05.plan_includes_non_vegetarian_item(output)


@given(
    tag=st.sampled_from(["ACTION", "action", " Action "]),
    value=st.sampled_from(["clarify", "proceed"]),
    pre=st.sampled_from(["", " ", "\t"]),
    post=st.sampled_from(["", " ", "\t"]),
)
def test_common_extract_tag_value_is_case_and_whitespace_tolerant(
    tag: str, value: str, pre: str, post: str
) -> None:
    output = f"{tag}:{pre}{value}{post}"
    parsed = COMMON.extract_tag_value(output, "ACTION")
    assert parsed is not None
    assert parsed.lower() == value


@given(
    line=st.sampled_from(
        [
            "TOOL: docker.",
            "TOOL: kubectl!",
            'TOOL: "docker"',
            "TOOL: 'kubectl'",
            "TOOL: Docker?",
        ]
    )
)
def test_demo04_selected_tool_accepts_harmless_tag_punctuation_or_quotes(line: str) -> None:
    tool = DEMO04.selected_tool(line)
    assert tool in {"docker", "kubectl"}


@given(
    line=st.sampled_from(
        [
            "Use docker now",
            "I recommend kubectl for this deployment",
            "choose docker",
            "run kubectl",
        ]
    )
)
def test_demo04_selected_tool_ignores_non_structured_free_text(line: str) -> None:
    # Demo 04 intentionally restricts fallback parsing to tagged/list-like lines
    # so incidental prose does not get interpreted as authoritative tool selection.
    assert DEMO04.selected_tool(line) is None


@given(
    value=st.sampled_from(["vegan curry", "VEGAN CURRY", " vegan   curry "]),
    punct=st.sampled_from(["", ".", "!", "?"]),
    quote=st.sampled_from(["", '"', "'", "“", "”"]),
)
def test_demo07_premise_match_accepts_case_whitespace_and_trailing_punctuation(
    value: str, punct: str, quote: str
) -> None:
    output = f"PREMISE: {quote}{value}{quote}{punct}\n- list item"
    assert DEMO07.premise_matches_expected(output)
