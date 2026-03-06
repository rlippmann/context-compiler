import json
import sys
from typing import TextIO

from . import create_engine
from .engine import Decision


def format_decision(decision: Decision) -> str:
    return json.dumps(decision, sort_keys=True, separators=(",", ":"))


def run_repl(in_stream: TextIO, out_stream: TextIO) -> None:
    engine = create_engine()

    for line in in_stream:
        user_input = line.rstrip("\n")
        if user_input.strip().lower() in {"exit", "quit"}:
            return
        decision = engine.step(user_input)
        print(format_decision(decision), file=out_stream)


def main() -> int:
    run_repl(sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
