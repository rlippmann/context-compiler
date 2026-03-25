"""Demo 7: prompt engineering and compiled state are complementary."""

import re

from context_compiler import State, create_engine
from demos.common import (
    build_baseline_messages,
    build_compiled_system_prompt,
    compact_user_turns,
    extract_tag_value,
    print_decision,
    print_host_check,
    print_messages,
    print_model_output,
    print_spec_report,
    print_user_inputs,
    yes_no,
)
from demos.llm_client import Message, complete_messages

DEMO_NAME = "07_prompt_engineering_comparison — prompt engineering + authoritative state"
EXPECTED_PREMISE = "vegan curry"
FINAL_REQUEST = (
    "Give me a dinner plan. First line must be PREMISE:<value>. "
    "Use the current premise and then provide a short shopping list."
)
USER_INPUTS = [
    "set premise vegan curry",
    "Side note: I am planning a train trip and need camera advice later.",
    "My coworkers mentioned chicken tikka and shrimp pasta in a brainstorm.",
    "We also discussed weather apps and museum tickets for the weekend.",
    (
        "Draft notes from another thread said beef stew, but those notes may be stale "
        "and mixed with unrelated chatter."
    ),
    FINAL_REQUEST,
]

WEAK_SYSTEM_PROMPT = "Be a helpful assistant."
STRONG_PROMPT_ENGINEERING_TEXT = (
    "You are a careful assistant.\n"
    "Task: determine the user's current premise for this thread and answer the final request.\n"
    "Rules:\n"
    "1) Prioritize explicit user directives over brainstorm noise and side notes.\n"
    "2) Keep the selected premise consistent across the response.\n"
    "3) If multiple ideas appear, use the current selected premise instead of popularity.\n"
    "4) First line must be exactly PREMISE:<value>."
)
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value.strip().lower())


def premise_matches_expected(output: str, expected_premise: str = EXPECTED_PREMISE) -> bool:
    premise = extract_tag_value(output, "PREMISE")
    if premise is None:
        return False
    return _normalize_text(premise) == _normalize_text(expected_premise)


def build_weak_messages(user_inputs: list[str]) -> list[Message]:
    return build_baseline_messages(user_inputs, baseline_system_prompt=WEAK_SYSTEM_PROMPT)


def build_strong_messages(user_inputs: list[str]) -> list[Message]:
    return build_baseline_messages(
        user_inputs,
        baseline_system_prompt=STRONG_PROMPT_ENGINEERING_TEXT,
    )


def build_compiler_messages(state: State, user_inputs: list[str]) -> list[Message]:
    compiled_prefix = build_compiled_system_prompt(state)
    compiler_system_prompt = f"{compiled_prefix}\n{STRONG_PROMPT_ENGINEERING_TEXT}"
    return build_baseline_messages(user_inputs, baseline_system_prompt=compiler_system_prompt)


def build_compact_compiler_messages(state: State, compacted_inputs: list[str]) -> list[Message]:
    return build_compiler_messages(state, compacted_inputs)


def _actual_summary(*, weak_pass: bool, strong_pass: bool, compiler_pass: bool) -> str:
    if not weak_pass and strong_pass and compiler_pass:
        return (
            "basic prompting drifted, better prompting held the premise, and "
            "prompting plus compiled state also held the premise"
        )
    if weak_pass and strong_pass and compiler_pass:
        return "all three paths held the premise in this run"
    if not strong_pass and compiler_pass:
        return (
            "better prompting alone drifted on premise, but prompting plus "
            "compiled state held the authoritative premise"
        )
    if strong_pass and not compiler_pass:
        return "better prompting held premise, but prompting plus compiled state did not"
    return "premise handling was inconsistent across paths"


def main() -> None:
    engine = create_engine()
    print_user_inputs(USER_INPUTS)

    for index, user_input in enumerate(USER_INPUTS, start=1):
        decision = engine.step(user_input)
        print_decision(f"turn {index}", decision, engine.state)

    weak_messages = build_weak_messages(USER_INPUTS)
    print_messages("weak-baseline", weak_messages)
    weak_output = complete_messages(weak_messages)
    print_model_output("Weak baseline", weak_output)

    strong_messages = build_strong_messages(USER_INPUTS)
    print_messages("strong-baseline", strong_messages)
    strong_output = complete_messages(strong_messages)
    print_model_output("Strong baseline", strong_output)

    compiler_messages = build_compiler_messages(engine.state, USER_INPUTS)
    print_messages("compiler-mediated (full)", compiler_messages)
    compiler_output = complete_messages(compiler_messages)
    print_model_output("Compiler-mediated (full)", compiler_output)

    compacted_inputs, compacted_state, compacted_prompt = compact_user_turns(USER_INPUTS)
    if compacted_prompt is not None:
        print_messages("compiler-mediated + compact", [])
        compact_output = f"[no call] clarification required: {compacted_prompt}"
        print_model_output("Compiler-mediated + compact", compact_output)
    else:
        compact_messages = build_compact_compiler_messages(compacted_state, compacted_inputs)
        print_messages("compiler-mediated + compact", compact_messages)
        compact_output = complete_messages(compact_messages)
        print_model_output("Compiler-mediated + compact", compact_output)

    weak_premise = extract_tag_value(weak_output, "PREMISE")
    strong_premise = extract_tag_value(strong_output, "PREMISE")
    compiler_premise = extract_tag_value(compiler_output, "PREMISE")
    compact_premise = extract_tag_value(compact_output, "PREMISE")
    weak_pass = premise_matches_expected(weak_output)
    strong_pass = premise_matches_expected(strong_output)
    compiler_pass = premise_matches_expected(compiler_output)
    compact_pass = compacted_prompt is None and premise_matches_expected(compact_output)

    compiled_prefix = build_compiled_system_prompt(engine.state)
    shared_prompt_text = compiler_messages[0]["content"].endswith(STRONG_PROMPT_ENGINEERING_TEXT)
    compiler_augmented_only = (
        compiler_messages[1:] == strong_messages[1:]
        and compiler_messages[0]["content"]
        == f"{compiled_prefix}\n{STRONG_PROMPT_ENGINEERING_TEXT}"
    )
    print_host_check(
        "WEAK_MATCHES_EXPECTED_PREMISE",
        f"{yes_no(weak_pass)}, premise_tag={weak_premise or 'MISSING'}",
        context="weak-baseline",
    )
    print_host_check(
        "STRONG_MATCHES_EXPECTED_PREMISE",
        f"{yes_no(strong_pass)}, premise_tag={strong_premise or 'MISSING'}",
        context="strong-baseline",
    )
    print_host_check(
        "COMPILER_MATCHES_EXPECTED_PREMISE",
        f"{yes_no(compiler_pass)}, premise_tag={compiler_premise or 'MISSING'}",
        context="compiler-mediated",
    )
    print_host_check(
        "COMPACT_MATCHES_EXPECTED_PREMISE",
        f"{yes_no(compact_pass)}, premise_tag={compact_premise or 'MISSING'}",
        context="compiler-mediated + compact",
    )
    print_host_check(
        "COMPILER_REUSES_STRONG_PROMPT_TEXT",
        yes_no(shared_prompt_text),
        context="compiler-mediated",
    )
    print_host_check(
        "COMPILER_ONLY_ADDS_COMPILED_STATE",
        yes_no(compiler_augmented_only),
        context="compiler-mediated",
    )

    demo_pass = (
        (not weak_pass)
        and strong_pass
        and compiler_pass
        and compact_pass
        and shared_prompt_text
        and compiler_augmented_only
    )
    print_spec_report(
        test_name=DEMO_NAME,
        baseline_pass=strong_pass,
        compiler_pass=compiler_pass,
        compiler_compact_pass=compact_pass,
        expected=(
            "prompting quality should help, and prompting plus compiled authoritative "
            "state should be most reliable; compiler-mediated prompting should reuse "
            "the same prompt text"
        ),
        actual=_actual_summary(
            weak_pass=weak_pass,
            strong_pass=strong_pass,
            compiler_pass=compiler_pass,
        ),
        passed=demo_pass,
        result_pass="prompting helps; authoritative compiled state adds reliability",
        result_fail=("three-way complementarity claim not established in this run"),
    )


if __name__ == "__main__":
    main()
