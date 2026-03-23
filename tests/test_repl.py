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


def test_repl_update_flow() -> None:
    decisions = _run_session("set premise concise\nquit\n")

    assert decisions == [
        {
            "kind": "update",
            "prompt_to_user": None,
            "state": {"premise": "concise", "policies": {}, "version": 2},
        }
    ]


def test_repl_clarify_flow() -> None:
    decisions = _run_session("don't use docker\nuse kubectl instead of docker\nquit\n")
    expected_prompt = (
        '"docker" is currently prohibited. Did you mean to remove it and use "kubectl" instead?'
    )

    assert decisions == [
        {
            "kind": "update",
            "prompt_to_user": None,
            "state": {"premise": None, "policies": {"docker": "prohibit"}, "version": 2},
        },
        {
            "kind": "clarify",
            "prompt_to_user": expected_prompt,
            "state": None,
        },
    ]


def test_repl_exit_and_quit_terminate_session() -> None:
    decisions_exit = _run_session("exit\nset premise concise\n")
    decisions_quit = _run_session("quit\nset premise concise\n")

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
