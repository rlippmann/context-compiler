from io import StringIO

from context_compiler.repl import (
    _normalize_confirmation_token,
    _print_command_error,
    _render_diff_lines,
    run_repl,
)


class _TTYStringIO(StringIO):
    def isatty(self) -> bool:
        return True


def test_render_diff_lines_covers_premise_removed_and_changed_policy() -> None:
    preview_result = {
        "output_version": 1,
        "mode": "preview",
        "decision": {
            "kind": "update",
            "state": {"premise": "next", "policies": {}},
            "prompt_to_user": None,
        },
        "state_before": {"premise": "before", "policies": {"docker": "use"}},
        "state_after": {"premise": "next", "policies": {"docker": "prohibit"}},
        "would_mutate": True,
        "diff": {
            "changed": True,
            "premise": {"before": "before", "after": "next", "changed": True},
            "policies": {
                "added": {},
                "removed": {"kubectl": "use"},
                "changed": {"docker": {"before": "use", "after": "prohibit"}},
            },
        },
    }

    lines = _render_diff_lines(preview_result)  # type: ignore[arg-type]
    assert "- premise: before -> next" in lines
    assert "- - use kubectl" in lines
    assert "- ~ use docker -> prohibit docker" in lines


def test_print_command_error_leading_blank_line() -> None:
    out = StringIO()
    _print_command_error(out, leading_blank=True, message="boom")
    assert out.getvalue().splitlines() == ["", "error: boom"]


def test_normalize_confirmation_token_strips_trailing_punctuation() -> None:
    assert _normalize_confirmation_token(" YES PLEASE!! ") == "yes please"


def test_interactive_state_step_and_preview_command_error_paths() -> None:
    out = _TTYStringIO()
    run_repl(
        _TTYStringIO("state\nstep\npreview\nquit\n"),
        out,
    )
    lines = out.getvalue().splitlines()

    assert "premise: (none)" in lines
    assert "policies: (none)" in lines
    assert "error: step requires input." in lines
    assert "Use 'step <input>'." in lines
    assert "error: preview requires input." in lines
    assert "Use 'preview <input>'." in lines
