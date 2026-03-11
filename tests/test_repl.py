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
    decisions = _run_session("use Nord Stage 4\nquit\n")

    assert len(decisions) == 1
    assert decisions[0]["kind"] == "update"
    assert decisions[0]["state"] == {
        "facts": {"focus.primary": "Nord Stage 4"},
        "policies": {"prohibit": []},
        "version": 1,
    }


def test_repl_clarify_flow() -> None:
    decisions = _run_session("no use docker\nquit\n")

    assert len(decisions) == 1
    assert decisions[0]["kind"] == "clarify"
    assert decisions[0]["state"] is None


def test_repl_state_persists_across_turns() -> None:
    decisions = _run_session("don't use docker\nallow docker\nquit\n")

    assert len(decisions) == 2
    assert decisions[0]["kind"] == "update"
    assert decisions[0]["state"] == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": ["docker"]},
        "version": 1,
    }
    assert decisions[1]["kind"] == "update"
    assert decisions[1]["state"] == {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": []},
        "version": 1,
    }


def test_repl_exit_and_quit_terminate_session() -> None:
    decisions_exit = _run_session("exit\nuse Nord Stage 4\n")
    decisions_quit = _run_session("quit\nuse Nord Stage 4\n")

    assert decisions_exit == []
    assert decisions_quit == []


def test_repl_interactive_help_commands() -> None:
    out = _TTYStringIO()
    run_repl(_TTYStringIO("help\n?\nquit\n"), out)

    lines = out.getvalue().splitlines()
    expected_help = [
        "Commands: help/? exit/quit",
        "Examples:",
        "  use chamber ensemble",
        "  don't use passive voice",
        "  allow contractions",
        "  actually piano reduction",
        "  reset policies",
        "  clear state",
    ]
    assert lines[0] == "Context Compiler REPL. Type help for commands."
    assert lines[1:9] == expected_help
    assert lines[9:17] == expected_help


def test_repl_interactive_ignores_blank_lines() -> None:
    out = _TTYStringIO()
    run_repl(_TTYStringIO("\n   \n\t\nquit\n"), out)

    assert out.getvalue().splitlines() == ["Context Compiler REPL. Type help for commands."]


def test_repl_interactive_formats_decisions_and_state_summary() -> None:
    out = _TTYStringIO()
    run_repl(_TTYStringIO("hello\nuse Nord Stage 4\nno use docker\nquit\n"), out)

    lines = out.getvalue().splitlines()
    assert lines[0] == "Context Compiler REPL. Type help for commands."
    assert lines[1] == "passthrough"
    assert lines[2] == "updated"
    assert lines[3] == "state:"
    assert lines[4] == '  focus.primary: "Nord Stage 4"'
    assert lines[5] == "  prohibit: []"
    assert lines[6].startswith("clarify: ")


def test_repl_interactive_eof_exits_cleanly() -> None:
    out = _TTYStringIO()
    run_repl(_TTYStringIO("use Nord Stage 4\n"), out)

    assert out.getvalue().splitlines() == [
        "Context Compiler REPL. Type help for commands.",
        "updated",
        "state:",
        '  focus.primary: "Nord Stage 4"',
        "  prohibit: []",
    ]


def test_repl_interactive_reset_policies_output() -> None:
    out = _TTYStringIO()
    run_repl(_TTYStringIO("don't use passive voice\nreset policies\nquit\n"), out)

    lines = out.getvalue().splitlines()
    assert lines == [
        "Context Compiler REPL. Type help for commands.",
        "updated",
        "state:",
        "  focus.primary: null",
        '  prohibit: ["passive voice"]',
        "updated",
        "state:",
        "  focus.primary: null",
        "  prohibit: []",
    ]


def test_repl_non_interactive_keeps_json_output() -> None:
    out = StringIO()
    run_repl(StringIO("use Nord Stage 4\nquit\n"), out)

    lines = out.getvalue().splitlines()
    expected = (
        '{"kind":"update","prompt_to_user":null,'
        '"state":{"facts":{"focus.primary":"Nord Stage 4"},'
        '"policies":{"prohibit":[]},"version":1}}'
    )
    assert lines == [expected]
