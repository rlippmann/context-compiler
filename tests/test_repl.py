import json
from io import StringIO

from context_compiler.repl import run_repl


class _TTYStringIO(StringIO):
    def isatty(self) -> bool:
        return True


def _run_session(text: str) -> list[dict[str, object]]:
    out = StringIO()
    run_repl(StringIO(text), out)
    lines = [line for line in out.getvalue().splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def test_repl_passthrough_flow() -> None:
    decisions = _run_session("hello\nquit\n")

    assert decisions == [{"kind": "passthrough", "prompt_to_user": None, "state": None}]


def test_repl_exit_and_quit_terminate_session() -> None:
    decisions_exit = _run_session("exit\nhello\n")
    decisions_quit = _run_session("quit\nhello\n")

    assert decisions_exit == []
    assert decisions_quit == []


def test_repl_interactive_help_commands() -> None:
    out = _TTYStringIO()
    run_repl(_TTYStringIO("help\n?\nquit\n"), out)

    lines = out.getvalue().splitlines()
    expected_help = [
        "Commands: help/? exit/quit",
        "Examples:",
        "  set premise concise replies",
        "  don't use docker",
        "  clear premise",
        "  reset policies",
        "  clear state",
    ]
    assert lines[0] == "Context Compiler REPL. Type help for commands."
    assert lines[1:8] == expected_help
    assert lines[8:15] == expected_help


def test_repl_non_interactive_keeps_json_output() -> None:
    out = StringIO()
    run_repl(StringIO("hello\nquit\n"), out)

    lines = out.getvalue().splitlines()
    expected = '{"kind":"passthrough","prompt_to_user":null,"state":null}'
    assert lines == [expected]
