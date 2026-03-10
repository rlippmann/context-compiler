import json
from io import StringIO

from context_compiler.repl import run_repl


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
