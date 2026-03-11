"""Demo 4: compiler state governs tool-choice constraints."""

import re

from context_compiler import create_engine
from context_compiler.const import POLICY_PROHIBIT, STATE_POLICIES
from demos.common import (
    build_baseline_messages,
    build_mediated_messages,
    extract_tag_value,
    is_verbose,
    print_decision,
    print_host_check,
    print_messages,
    print_model_output,
    print_spec_report,
    print_tag_comparison,
    print_user_inputs,
)
from demos.llm_client import complete_messages

_TOOL_TAG_RE = re.compile(r"(?im)^\s*tool\s*:\s*(docker|kubectl)\s*$")
_ACTION_TOOL_RE = re.compile(
    r"(?im)\b(?:use|run|deploy with|recommend(?:ed)?|choose)\s+(docker|kubectl)\b"
)
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+")


def selected_tool(output: str) -> str | None:
    tagged = extract_tag_value(output, "TOOL")
    if tagged is not None and tagged.lower() in {"docker", "kubectl"}:
        return tagged.lower()

    tag_match = _TOOL_TAG_RE.search(output)
    if tag_match is not None:
        return tag_match.group(1).lower()

    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not _LIST_ITEM_RE.match(stripped) and ":" not in stripped:
            continue
        action_match = _ACTION_TOOL_RE.search(stripped)
        if action_match is not None:
            return action_match.group(1).lower()
    return None


def main() -> None:
    engine = create_engine()
    user_inputs = [
        "don't use docker",
        (
            "Deploy the service. Pick one tool from docker, kubectl. "
            "First line must be TOOL:<docker|kubectl> and second line ACTION:<one-line action>."
        ),
    ]
    print_user_inputs(user_inputs)

    first = engine.step(user_inputs[0])
    print_decision("turn 1", first, engine.state)

    second = engine.step(user_inputs[1])
    print_decision("turn 2", second, engine.state)

    baseline_messages = build_baseline_messages(
        [user_inputs[1]],
        baseline_system_prompt="Recommend a practical approach using the available tools.",
    )
    print_messages("baseline", baseline_messages)
    baseline_output = complete_messages(baseline_messages)
    print_model_output("Baseline", baseline_output)

    prohibited = engine.state[STATE_POLICIES][POLICY_PROHIBIT]
    candidate_tools = ["docker", "kubectl"]
    filtered_tools = [tool for tool in candidate_tools if tool not in prohibited]
    if is_verbose():
        print("Candidate tools before filtering:")
        print(", ".join(candidate_tools))
        print()
        print("Candidate tools after applying compiler denylist:")
        print(", ".join(filtered_tools) if filtered_tools else "(none)")
        print()

    mediated_messages = build_mediated_messages(
        engine.state,
        user_inputs[1],
        extra_system_prompt=(
            "Only choose tools that are not prohibited."
            + "\nCandidate tools: "
            + f"{', '.join(candidate_tools)}. "
            + f"Prohibited: {', '.join(prohibited) or '(none)'}"
        ),
    )
    print_messages("compiler-mediated", mediated_messages)
    mediated_output = complete_messages(mediated_messages)
    print_model_output("Compiler-mediated", mediated_output)
    print_tag_comparison("TOOL", baseline_output, mediated_output)
    baseline_tool = selected_tool(baseline_output)
    mediated_tool = selected_tool(mediated_output)
    baseline_respects = baseline_tool is not None and baseline_tool not in prohibited
    mediated_respects = mediated_tool is not None and mediated_tool not in prohibited
    print_host_check("SELECTED_TOOL", baseline_tool or "MISSING", context="baseline")
    print_host_check(
        "SELECTED_TOOL",
        mediated_tool or "MISSING",
        context="compiler-mediated",
    )
    print_spec_report(
        test_name="04_tool_governance — denylisted tool selection",
        baseline_pass=baseline_respects,
        compiler_pass=mediated_respects,
        expected="compiler-mediated should select an allowed tool and avoid the denylisted one",
        actual=(
            f"baseline selected {baseline_tool or 'no clear tool'}; "
            f"compiler-mediated selected allowed tool {mediated_tool or 'no clear tool'}"
            if mediated_respects
            else (
                f"baseline selected {baseline_tool or 'no clear tool'}; "
                "compiler-mediated selected a prohibited tool "
                f"or no clear tool ({mediated_tool or 'none'})"
            )
        ),
        passed=mediated_respects,
        result_pass="denylisted tool avoided",
        result_fail="denylisted tool not avoided",
    )


if __name__ == "__main__":
    main()
