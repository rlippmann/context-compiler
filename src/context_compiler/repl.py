import sys
from typing import TextIO

from . import create_engine, get_policy_items, get_premise_value
from .engine import Decision, DecisionKind, State

_EXIT_TOKENS = {"exit", "quit"}
_HELP_TOKENS = {"help", "?"}
_MULTI_COMMAND_PROMPT = "Multiple commands detected.\nEnter one command per line."


def _is_interactive(in_stream: TextIO, out_stream: TextIO) -> bool:
    return bool(in_stream.isatty() and out_stream.isatty())


def _has_embedded_newline(raw_line: str) -> bool:
    body = raw_line[:-1] if raw_line.endswith("\n") else raw_line
    if body.endswith("\r"):
        body = body[:-1]
    return "\n" in body or "\r" in body


def _multi_command_decision() -> Decision:
    return {
        "kind": DecisionKind.CLARIFY,
        "state": None,
        "prompt_to_user": _MULTI_COMMAND_PROMPT,
    }


def _print_interactive_help(out_stream: TextIO) -> None:
    print("Commands: help/? exit/quit", file=out_stream)
    print("Directives (exact prefix only):", file=out_stream)
    print("  set premise <value>", file=out_stream)
    print("  change premise to <value>", file=out_stream)
    print("  use <item>", file=out_stream)
    print("  prohibit <item>", file=out_stream)
    print("  remove policy <item>", file=out_stream)
    print("  use <new item> instead of <old item>", file=out_stream)
    print("  clear premise", file=out_stream)
    print("  reset policies", file=out_stream)
    print("  clear state", file=out_stream)
    print("Only question prompts accept yes/no confirmations", file=out_stream)
    print("Other clarify prompts are errors and do not accept yes/no", file=out_stream)


def _render_state_lines(state: State) -> list[str]:
    premise = get_premise_value(state)
    premise_line = "premise: (none)" if premise is None else f"premise: {premise}"

    all_policy_items = get_policy_items(state)
    if not all_policy_items:
        return [premise_line, "policies: (none)"]

    use_items = set(get_policy_items(state, "use"))
    policy_items: list[tuple[str, str]] = []
    for item in all_policy_items:
        value = "use" if item in use_items else "prohibit"
        policy_items.append((item, value))
    if not policy_items:
        return [premise_line, "policies: (none)"]

    lines = [premise_line, "policies:"]
    for item, value in policy_items:
        lines.append(f"- {value} {item}")
    return lines


def _render_decision_lines(decision: Decision) -> list[str]:
    kind = decision["kind"]
    if kind == "passthrough":
        return ["passthrough"]
    if kind == "clarify":
        prompt = decision["prompt_to_user"] or ""
        prompt_lines = prompt.splitlines() if prompt else [""]
        if prompt.endswith("?"):
            return [f"confirm: {prompt_lines[0]}", *prompt_lines[1:]]
        return [f"error: {prompt_lines[0]}", *prompt_lines[1:]]

    state = decision["state"]
    assert state is not None
    return ["updated", *_render_state_lines(state)]


def _print_decision_lines(decision: Decision, out_stream: TextIO, *, leading_blank: bool) -> None:
    if leading_blank:
        print("", file=out_stream)
    for line in _render_decision_lines(decision):
        print(line, file=out_stream)


def run_repl(in_stream: TextIO, out_stream: TextIO) -> None:
    engine = create_engine()

    if _is_interactive(in_stream, out_stream):
        print("Context Compiler REPL (0.5). Type help for commands.", file=out_stream)
        print("Non-directive input is passthrough.", file=out_stream)

        while True:
            line = in_stream.readline()
            if line == "":
                return
            if _has_embedded_newline(line):
                _print_decision_lines(_multi_command_decision(), out_stream, leading_blank=True)
                continue
            user_input = line.rstrip("\n")
            token = user_input.strip().lower()
            if not token:
                continue
            if token in _EXIT_TOKENS:
                return
            if token in _HELP_TOKENS:
                _print_interactive_help(out_stream)
                continue

            decision = engine.step(user_input)
            _print_decision_lines(decision, out_stream, leading_blank=True)
        return

    for line in in_stream:
        if _has_embedded_newline(line):
            _print_decision_lines(_multi_command_decision(), out_stream, leading_blank=False)
            continue
        user_input = line.rstrip("\n")
        if user_input.strip().lower() in _EXIT_TOKENS:
            return
        decision = engine.step(user_input)
        _print_decision_lines(decision, out_stream, leading_blank=False)


def main() -> int:  # pragma: no cover
    run_repl(sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
