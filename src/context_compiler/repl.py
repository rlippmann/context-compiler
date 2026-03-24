import json
import sys
from typing import TextIO

from . import create_engine
from .engine import Decision, DecisionKind

_EXIT_TOKENS = {"exit", "quit"}
_HELP_TOKENS = {"help", "?"}
_MULTI_COMMAND_PROMPT = "Multiple commands detected.\nEnter one command per line."


def format_decision(decision: Decision) -> str:
    return json.dumps(decision, sort_keys=True, separators=(",", ":"))


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
    print("  use <new item> instead of <old item>", file=out_stream)
    print("  clear premise", file=out_stream)
    print("  reset policies", file=out_stream)
    print("  clear state", file=out_stream)
    print("Only question prompts accept yes/no confirmations", file=out_stream)
    print("Other clarify prompts are errors and do not accept yes/no", file=out_stream)
    print('State schema: {"premise": ..., "policies": ..., "version": 2}', file=out_stream)


def _print_interactive_decision(decision: Decision, out_stream: TextIO) -> None:
    print("", file=out_stream)
    kind = decision["kind"]
    if kind == "passthrough":
        print("passthrough", file=out_stream)
        return
    if kind == "clarify":
        prompt = decision["prompt_to_user"] or ""
        if prompt.endswith("?"):
            print(f"confirm: {prompt}", file=out_stream)
        else:
            print(f"error: {prompt}", file=out_stream)
        return

    print("updated", file=out_stream)
    state = decision["state"]
    assert state is not None
    print("state:", file=out_stream)
    print(json.dumps(state, sort_keys=True), file=out_stream)


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
                _print_interactive_decision(_multi_command_decision(), out_stream)
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
            _print_interactive_decision(decision, out_stream)
        return

    for line in in_stream:
        if _has_embedded_newline(line):
            print(format_decision(_multi_command_decision()), file=out_stream)
            continue
        user_input = line.rstrip("\n")
        if user_input.strip().lower() in _EXIT_TOKENS:
            return
        decision = engine.step(user_input)
        print(format_decision(decision), file=out_stream)


def main() -> int:  # pragma: no cover
    run_repl(sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
