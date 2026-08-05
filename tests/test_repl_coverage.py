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
