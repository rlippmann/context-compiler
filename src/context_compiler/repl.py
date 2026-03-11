import json
import sys
from typing import TextIO

from . import create_engine
from .engine import Decision

_EXIT_TOKENS = {"exit", "quit"}
_HELP_TOKENS = {"help", "?"}


def format_decision(decision: Decision) -> str:
    return json.dumps(decision, sort_keys=True, separators=(",", ":"))


def _is_interactive(in_stream: TextIO, out_stream: TextIO) -> bool:
    return bool(in_stream.isatty() and out_stream.isatty())


def _print_interactive_help(out_stream: TextIO) -> None:
    print("Commands: help/? exit/quit", file=out_stream)
    print("Examples:", file=out_stream)
    print("  use chamber ensemble", file=out_stream)
    print("  don't use passive voice", file=out_stream)
    print("  allow contractions", file=out_stream)
    print("  actually piano reduction", file=out_stream)
    print("  reset policies", file=out_stream)
    print("  clear state", file=out_stream)


def _print_interactive_decision(decision: Decision, out_stream: TextIO) -> None:
    kind = decision["kind"]
    if kind == "passthrough":
        print("passthrough", file=out_stream)
        return
    if kind == "clarify":
        prompt = decision["prompt_to_user"] or ""
        print(f"clarify: {prompt}", file=out_stream)
        return

    print("updated", file=out_stream)
    state = decision["state"]
    assert state is not None
    focus_primary = state["facts"]["focus.primary"]
    prohibit = state["policies"]["prohibit"]
    print("state:", file=out_stream)
    print(f"  focus.primary: {json.dumps(focus_primary)}", file=out_stream)
    print(f"  prohibit: {json.dumps(prohibit)}", file=out_stream)


def run_repl(in_stream: TextIO, out_stream: TextIO) -> None:
    engine = create_engine()

    if _is_interactive(in_stream, out_stream):
        print("Context Compiler REPL. Type help for commands.", file=out_stream)

        while True:
            line = in_stream.readline()
            if line == "":
                return
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
        user_input = line.rstrip("\n")
        if user_input.strip().lower() in _EXIT_TOKENS:
            return
        decision = engine.step(user_input)
        print(format_decision(decision), file=out_stream)


def main() -> int:
    run_repl(sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
