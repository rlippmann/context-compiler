"""Demo 2: baseline prompt can drift from persistent constraints."""

import re

from context_compiler import create_engine
from demos.common import (
    build_baseline_messages,
    build_mediated_messages_from_transcript,
    compact_user_turns,
    print_decision,
    print_host_check,
    print_messages,
    print_model_output,
    print_spec_report,
    print_user_inputs,
    yes_no,
)
from demos.llm_client import complete_messages

_REFUSAL_PATTERNS = (
    r"\b(can(?:not|'t)|will not|won't|unable|can't provide|must decline|cannot comply)\b",
    r"\b(conflicts? with|not allowed|prohibited|policy)\b",
)
_SAFE_ALTERNATIVE_PATTERNS = (
    r"\b(peanut[- ]free|without peanuts?)\b",
    r"\b(instead|alternative)\b",
)
_RECIPE_HEADING_RE = re.compile(
    r"^\s*(ingredients?|steps?|instructions?|directions?|method|preparation)\s*:\s*(.*)$",
    flags=re.IGNORECASE,
)
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+")
_TITLE_HINT_RE = re.compile(r"\b(recipe|curry)\b", flags=re.IGNORECASE)
_PROHIBITED_RE = re.compile(r"\bpeanuts?\b", flags=re.IGNORECASE)
_STYLE_REFERENCE_RE = re.compile(r"\bpeanut[- ]style\b", flags=re.IGNORECASE)
_NEGATION_RE = re.compile(
    r"\b(no|without|avoid|exclude|free of|peanut-free)\b", flags=re.IGNORECASE
)


def refusal_detected(output: str) -> bool:
    lowered = output.lower()
    return any(re.search(pattern, lowered) for pattern in _REFUSAL_PATTERNS)


def safe_alternative_detected(output: str) -> bool:
    lowered = output.lower()
    return any(re.search(pattern, lowered) for pattern in _SAFE_ALTERNATIVE_PATTERNS)


def _is_refusal_line(line: str) -> bool:
    lowered = line.lower()
    return any(re.search(pattern, lowered) for pattern in _REFUSAL_PATTERNS)


def _recipe_lines(output: str) -> list[str]:
    lines = output.splitlines()
    recipe_lines: list[str] = []
    in_section = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        heading_match = _RECIPE_HEADING_RE.match(stripped)
        if heading_match:
            in_section = True
            remainder = heading_match.group(2).strip()
            if remainder:
                recipe_lines.append(remainder)
            continue

        if in_section:
            recipe_lines.append(stripped)
            continue

        if _LIST_ITEM_RE.match(stripped):
            recipe_lines.append(stripped)
            continue

        if index < 4 and _TITLE_HINT_RE.search(stripped) and not _is_refusal_line(stripped):
            recipe_lines.append(stripped)

    return recipe_lines


def recipe_includes_prohibited_item(output: str) -> bool:
    for line in _recipe_lines(output):
        if not _PROHIBITED_RE.search(line):
            continue
        if _STYLE_REFERENCE_RE.search(line):
            continue
        if _NEGATION_RE.search(line):
            continue
        if _is_refusal_line(line):
            continue
        return True
    return False


def main() -> None:
    engine = create_engine()
    user_inputs = [
        "prohibit peanuts",
        "Suggest a peanut curry recipe with ingredients and steps.",
    ]
    print_user_inputs(user_inputs)

    first = engine.step(user_inputs[0])
    print_decision("turn 1", first, engine.state)

    second = engine.step(user_inputs[1])
    print_decision("turn 2", second, engine.state)

    baseline_messages = build_baseline_messages(
        [user_inputs[1]],
        baseline_system_prompt="Be a helpful assistant. Provide clear and practical suggestions.",
    )
    print_messages("baseline", baseline_messages)
    baseline_output = complete_messages(baseline_messages)
    print_model_output("Baseline", baseline_output)
    baseline_refusal = refusal_detected(baseline_output)
    baseline_violation = recipe_includes_prohibited_item(baseline_output)
    print_host_check("REFUSAL_DETECTED", yes_no(baseline_refusal), context="baseline")
    print_host_check(
        "RECIPE_INCLUDES_PROHIBITED",
        yes_no(baseline_violation),
        context="baseline",
    )

    mediated_messages = build_mediated_messages_from_transcript(
        engine.state,
        user_inputs,
        extra_system_prompt=(
            "If the user requests a prohibited item, refuse the literal request. "
            "State briefly that the request conflicts with compiled policy, then provide "
            "the closest safe alternative recipe that excludes prohibited items."
        ),
    )
    print_messages("compiler-mediated (full)", mediated_messages)
    mediated_output = complete_messages(mediated_messages)
    print_model_output("Compiler-mediated (full)", mediated_output)
    mediated_refusal = refusal_detected(mediated_output)
    mediated_safe_alternative = safe_alternative_detected(mediated_output)
    mediated_violation = recipe_includes_prohibited_item(mediated_output)

    compacted_turns, compacted_state, compacted_prompt = compact_user_turns(user_inputs)
    if compacted_prompt is not None:
        print_messages("compiler-mediated + compact", [])
        compact_output = f"[no call] clarification required: {compacted_prompt}"
        print_model_output("Compiler-mediated + compact", compact_output)
        compact_refusal = True
        compact_violation = False
    else:
        compact_messages = build_mediated_messages_from_transcript(
            compacted_state,
            compacted_turns,
            extra_system_prompt=(
                "If the user requests a prohibited item, refuse the literal request. "
                "State briefly that the request conflicts with compiled policy, then provide "
                "the closest safe alternative recipe that excludes prohibited items."
            ),
        )
        print_messages("compiler-mediated + compact", compact_messages)
        compact_output = complete_messages(compact_messages)
        print_model_output("Compiler-mediated + compact", compact_output)
        compact_refusal = refusal_detected(compact_output)
        compact_safe_alternative = safe_alternative_detected(compact_output)
        compact_violation = recipe_includes_prohibited_item(compact_output)
    if compacted_prompt is not None:
        compact_safe_alternative = True

    print_host_check(
        "REFUSAL_DETECTED",
        yes_no(mediated_refusal),
        context="compiler-mediated (full)",
    )
    print_host_check(
        "RECIPE_INCLUDES_PROHIBITED",
        yes_no(mediated_violation),
        context="compiler-mediated (full)",
    )
    print_host_check(
        "SAFE_ALTERNATIVE_DETECTED",
        yes_no(mediated_safe_alternative),
        context="compiler-mediated (full)",
    )
    print_host_check(
        "REFUSAL_DETECTED",
        yes_no(compact_refusal),
        context="compiler-mediated + compact",
    )
    print_host_check(
        "RECIPE_INCLUDES_PROHIBITED",
        yes_no(compact_violation),
        context="compiler-mediated + compact",
    )
    print_host_check(
        "SAFE_ALTERNATIVE_DETECTED",
        yes_no(compact_safe_alternative),
        context="compiler-mediated + compact",
    )
    baseline_pass = not baseline_violation
    compiler_pass = (mediated_refusal or mediated_safe_alternative) and not mediated_violation
    compact_pass = (compact_refusal or compact_safe_alternative) and not compact_violation
    passed = baseline_violation and compiler_pass and compact_pass
    print_spec_report(
        test_name="02_constraint_drift — persistent prohibition",
        baseline_pass=baseline_pass,
        compiler_pass=compiler_pass,
        compiler_compact_pass=compact_pass,
        expected=(
            "compiler-mediated should refuse the prohibited request and offer a safe alternative"
        ),
        actual=(
            "baseline produced peanut recipe; both compiler-mediated paths "
            "refused and offered peanut-free alternatives"
            if baseline_violation and compiler_pass and compact_pass
            else (
                "baseline gave peanut recipe; compiler-mediated response did not clearly refuse "
                "or still included prohibited content"
                if baseline_violation
                else (
                    "baseline did not include prohibited recipe content; "
                    "compiler-mediated handling did not show a clear improvement"
                )
            )
        ),
        passed=passed,
        result_pass="prohibition enforced",
        result_fail="prohibition not enforced",
    )


if __name__ == "__main__":
    main()
