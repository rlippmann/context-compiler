from io import StringIO

from context_compiler.repl import _print_command_error, run_repl


class _TTYStringIO(StringIO):
    def isatty(self) -> bool:
        return True


def test_print_command_error_leading_blank_line() -> None:
    out = StringIO()
    _print_command_error(out, leading_blank=True, message="boom")
    assert out.getvalue().splitlines() == ["", "error: boom"]


def test_interactive_state_and_step_command_error_paths() -> None:
    out = _TTYStringIO()
    run_repl(
        _TTYStringIO("state\nstep\nquit\n"),
        out,
    )
    lines = out.getvalue().splitlines()

    assert "premise: (none)" in lines
    assert "policies: (none)" in lines
    assert "error: step requires input." in lines
    assert "Use 'step <input>'." in lines


def test_interactive_semantic_error_renders_human_message() -> None:
    out = _TTYStringIO()
    run_repl(
        _TTYStringIO("prohibit docker\nuse docker\nquit\n"),
        out,
    )
    lines = out.getvalue().splitlines()

    assert 'error: "docker" is currently prohibited.' in lines
    assert "Remove or replace it before using it." in lines


def test_non_interactive_json_no_directive_decision() -> None:
    out = StringIO()
    run_repl(StringIO("ordinary text\nquit\n"), out, json_mode=True)

    assert out.getvalue().splitlines() == [
        '{"command":"input","decision":{"kind":"no_directive","message":null},'
        '"mode":"step","output_version":2,"state":{"policies":{},"premise":null,"version":2}}'
    ]
