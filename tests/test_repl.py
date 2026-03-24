from io import StringIO

from context_compiler.repl import run_repl


class _TTYStringIO(StringIO):
    def isatty(self) -> bool:
        return True


class _ChunkedTTYInput:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    def readline(self) -> str:
        if not self._chunks:
            return ""
        return self._chunks.pop(0)

    def isatty(self) -> bool:
        return True


class _ChunkedInput:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    def __iter__(self) -> "_ChunkedInput":
        return self

    def __next__(self) -> str:
        if not self._chunks:
            raise StopIteration
        return self._chunks.pop(0)

    def isatty(self) -> bool:
        return False


def _run_interactive_lines(text: str) -> list[str]:
    out = _TTYStringIO()
    run_repl(_TTYStringIO(text), out)
    return [line for line in out.getvalue().splitlines() if line.strip()]


def _run_non_interactive_lines(text: str) -> list[str]:
    out = StringIO()
    run_repl(StringIO(text), out)
    return [line for line in out.getvalue().splitlines() if line.strip()]


def _contains_subsequence(lines: list[str], expected: list[str]) -> bool:
    window = len(expected)
    if window == 0 or window > len(lines):
        return False
    return any(lines[i : i + window] == expected for i in range(len(lines) - window + 1))


def test_repl_update_flow() -> None:
    lines = _run_non_interactive_lines("set premise concise\nquit\n")
    assert lines == ["updated", "premise: concise", "policies: (none)"]


def test_repl_clarify_flow() -> None:
    lines = _run_non_interactive_lines("prohibit docker\nuse kubectl instead of docker\nquit\n")
    assert _contains_subsequence(
        lines, ["updated", "premise: (none)", "policies:", "- prohibit docker"]
    )
    assert (
        'confirm: "docker" is currently prohibited. Did you mean to remove it and use '
        '"kubectl" instead?' in lines
    )


def test_repl_exit_and_quit_terminate_session() -> None:
    lines_exit = _run_non_interactive_lines("exit\nset premise concise\n")
    lines_quit = _run_non_interactive_lines("quit\nset premise concise\n")

    assert lines_exit == []
    assert lines_quit == []


def test_repl_interactive_help_commands() -> None:
    out = _TTYStringIO()
    run_repl(_TTYStringIO("help\n?\nquit\n"), out)

    lines = out.getvalue().splitlines()
    expected_help = [
        "Commands: help/? exit/quit",
        "Directives (exact prefix only):",
        "  set premise <value>",
        "  change premise to <value>",
        "  use <item>",
        "  prohibit <item>",
        "  remove policy <item>",
        "  use <new item> instead of <old item>",
        "  clear premise",
        "  reset policies",
        "  clear state",
        "Only question prompts accept yes/no confirmations",
        "Other clarify prompts are errors and do not accept yes/no",
    ]
    assert lines[0] == "Context Compiler REPL (0.5). Type help for commands."
    assert lines[1] == "Non-directive input is passthrough."
    assert lines[2:15] == expected_help
    assert lines[15:28] == expected_help


def test_repl_non_interactive_uses_human_readable_output() -> None:
    out = StringIO()
    run_repl(StringIO("hello\nquit\n"), out)

    lines = out.getvalue().splitlines()
    assert lines == ["passthrough"]


def test_repl_interactive_rejects_multi_command_chunk() -> None:
    out = _TTYStringIO()
    run_repl(
        _ChunkedTTYInput(["set premise concise\nprohibit peanuts\n", "quit\n"]),  # type: ignore[arg-type]
        out,
    )

    lines = out.getvalue().splitlines()
    assert "error: Multiple commands detected." in lines
    assert "Enter one command per line." in lines
    assert "updated" not in lines


def test_repl_non_interactive_rejects_multi_command_chunk_with_human_readable_clarify() -> None:
    out = StringIO()
    run_repl(
        _ChunkedInput(["set premise concise\nprohibit peanuts\n", "quit\n"]),  # type: ignore[arg-type]
        out,
    )

    lines = out.getvalue().splitlines()
    assert lines == ["error: Multiple commands detected.", "Enter one command per line."]


def test_repl_invalid_directive_near_misses_remain_passthrough() -> None:
    lines = _run_non_interactive_lines("actually use uv\nno use peanuts\nallow docker\nquit\n")
    assert lines == ["passthrough", "passthrough", "passthrough"]


def test_repl_non_interactive_remove_policy_flow() -> None:
    lines = _run_non_interactive_lines(
        "use docker\nremove policy docker\nremove policy podman\nquit\n"
    )
    assert _contains_subsequence(lines, ["updated", "premise: (none)", "policies:", "- use docker"])
    assert lines.count("updated") == 3
    assert lines.count("policies: (none)") == 2


def test_repl_contradiction_clarify_is_not_pending_confirmable() -> None:
    lines = _run_non_interactive_lines("use docker\nprohibit docker\nno\nquit\n")
    assert _contains_subsequence(lines, ["updated", "premise: (none)", "policies:", "- use docker"])
    assert _contains_subsequence(
        lines,
        [
            "error: 'docker' is already in use.",
            "Only one policy per item is allowed.",
            "Use 'reset policies' to change it.",
            "passthrough",
        ],
    )


def test_repl_replacement_clarify_requires_confirmation_tokens_and_persists_until_resolved() -> (
    None
):
    lines = _run_non_interactive_lines("use podman instead of docker\nmaybe\nyes please!!\nquit\n")
    assert lines.count('confirm: No exact policy found for "docker".') == 2
    assert lines.count("Replacement requires an exact policy match.") == 2
    assert lines.count('Confirm to use "podman" and keep existing policies?') == 2
    assert _contains_subsequence(lines, ["updated", "premise: (none)", "policies:", "- use podman"])


def test_repl_interactive_prints_confirm_and_error_for_clarify_types() -> None:
    error_out = _TTYStringIO()
    run_repl(_TTYStringIO("use docker\nprohibit docker\nquit\n"), error_out)
    error_lines = error_out.getvalue().splitlines()
    assert "error: 'docker' is already in use." in error_lines
    assert "Only one policy per item is allowed." in error_lines
    assert "Use 'reset policies' to change it." in error_lines

    confirm_out = _TTYStringIO()
    run_repl(_TTYStringIO("use podman instead of docker\nquit\n"), confirm_out)
    confirm_lines = confirm_out.getvalue().splitlines()
    assert 'confirm: No exact policy found for "docker".' in confirm_lines
    assert "Replacement requires an exact policy match." in confirm_lines
    assert 'Confirm to use "podman" and keep existing policies?' in confirm_lines


def test_repl_replacement_negative_confirmation_returns_update_unchanged_and_clears_pending() -> (
    None
):
    lines = _run_non_interactive_lines(
        "use docker\nprohibit podman\nuse podman instead of docker\nno\nno\nquit\n"
    )

    assert lines.count("updated") == 3
    assert _contains_subsequence(
        lines,
        [
            "updated",
            "premise: (none)",
            "policies:",
            "- use docker",
            "updated",
            "premise: (none)",
            "policies:",
            "- use docker",
            "- prohibit podman",
        ],
    )
    assert (
        'confirm: "podman" is currently prohibited. Did you mean to remove "docker" and use '
        '"podman" instead?' in lines
    )
    assert lines[-1] == "passthrough"


def test_repl_premise_lifecycle_outputs_expected_state_shape() -> None:
    lines = _run_non_interactive_lines(
        "set premise Use concise answers\n"
        "set premise Use verbose answers\n"
        "change premise to Use verbose answers\n"
        "quit\n"
    )

    assert _contains_subsequence(
        lines, ["updated", "premise: Use concise answers", "policies: (none)"]
    )
    assert _contains_subsequence(
        lines,
        [
            "error: Premise already exists.",
            "Use 'change premise to ...' to replace it.",
            "Premise is a single slot.",
            "To keep multiple ideas, rewrite them as one premise value.",
        ],
    )
    assert _contains_subsequence(
        lines, ["updated", "premise: Use verbose answers", "policies: (none)"]
    )


def test_repl_interactive_renders_updated_state_blocks_for_multiple_operations() -> None:
    lines = _run_interactive_lines("set premise concise replies\nuse docker\nclear premise\nquit\n")
    assert "updated" in lines
    assert _contains_subsequence(lines, ["updated", "premise: concise replies", "policies: (none)"])
    assert _contains_subsequence(
        lines, ["updated", "premise: concise replies", "policies:", "- use docker"]
    )
    assert _contains_subsequence(lines, ["updated", "premise: (none)", "policies:", "- use docker"])


def test_repl_interactive_confirmation_token_variants_resolve_pending_clarify() -> None:
    lines_yes = _run_interactive_lines("use podman instead of docker\nyeah\nquit\n")
    assert 'confirm: No exact policy found for "docker".' in lines_yes
    assert "Replacement requires an exact policy match." in lines_yes
    assert 'Confirm to use "podman" and keep existing policies?' in lines_yes
    assert _contains_subsequence(
        lines_yes, ["updated", "premise: (none)", "policies:", "- use podman"]
    )

    lines_ok = _run_interactive_lines("use buildah instead of docker\nok\nquit\n")
    assert 'confirm: No exact policy found for "docker".' in lines_ok
    assert "Replacement requires an exact policy match." in lines_ok
    assert 'Confirm to use "buildah" and keep existing policies?' in lines_ok
    assert _contains_subsequence(
        lines_ok, ["updated", "premise: (none)", "policies:", "- use buildah"]
    )

    lines_nope = _run_interactive_lines("use nerdctl instead of docker\nnope\nquit\n")
    assert 'confirm: No exact policy found for "docker".' in lines_nope
    assert "Replacement requires an exact policy match." in lines_nope
    assert 'Confirm to use "nerdctl" and keep existing policies?' in lines_nope
    assert _contains_subsequence(lines_nope, ["updated", "premise: (none)", "policies: (none)"])

    lines_no_thanks = _run_interactive_lines("use helm instead of docker\nno thanks\nquit\n")
    assert 'confirm: No exact policy found for "docker".' in lines_no_thanks
    assert "Replacement requires an exact policy match." in lines_no_thanks
    assert 'Confirm to use "helm" and keep existing policies?' in lines_no_thanks
    assert _contains_subsequence(
        lines_no_thanks, ["updated", "premise: (none)", "policies: (none)"]
    )


def test_repl_interactive_admin_idempotency_outputs_updated_with_unchanged_state() -> None:
    lines = _run_interactive_lines("clear premise\nclear state\nreset policies\nquit\n")

    assert lines.count("updated") == 3
    assert lines.count("premise: (none)") == 3
    assert lines.count("policies: (none)") == 3


def test_repl_interactive_confirm_vs_error_alignment_for_actual_clarify_behaviors() -> None:
    lines = _run_interactive_lines(
        "set premise concise\n"
        "set premise verbose\n"
        "use docker\n"
        "prohibit docker\n"
        "use podman instead of buildx\n"
        "quit\n"
    )

    assert ("error: Premise already exists.") in lines
    assert "Use 'change premise to ...' to replace it." in lines
    assert "Premise is a single slot." in lines
    assert "To keep multiple ideas, rewrite them as one premise value." in lines
    assert ("error: 'docker' is already in use.") in lines
    assert "Only one policy per item is allowed." in lines
    assert "Use 'reset policies' to change it." in lines
    assert 'confirm: No exact policy found for "buildx".' in lines
    assert "Replacement requires an exact policy match." in lines
    assert 'Confirm to use "podman" and keep existing policies?' in lines


def test_repl_interactive_passthrough_prints_passthrough_label() -> None:
    lines = _run_interactive_lines("actually use uv\nquit\n")
    assert "passthrough" in lines


def test_repl_interactive_blank_line_is_ignored_without_output() -> None:
    lines = _run_interactive_lines("\nset premise concise\nquit\n")

    assert lines[0] == "Context Compiler REPL (0.5). Type help for commands."
    assert lines[1] == "Non-directive input is passthrough."
    assert lines.count("updated") == 1
    assert _contains_subsequence(lines, ["updated", "premise: concise", "policies: (none)"])


def test_repl_interactive_eof_returns_cleanly_after_startup_banner() -> None:
    lines = _run_interactive_lines("")
    assert lines == [
        "Context Compiler REPL (0.5). Type help for commands.",
        "Non-directive input is passthrough.",
    ]


def test_repl_interactive_prints_blank_line_before_updated_decision() -> None:
    out = _TTYStringIO()
    run_repl(_TTYStringIO("set premise concise\nquit\n"), out)
    text = out.getvalue()

    assert "\n\nupdated\npremise: concise\n" in text


def test_repl_interactive_prints_blank_line_before_error_decision() -> None:
    out = _TTYStringIO()
    run_repl(_TTYStringIO("set premise concise\nset premise verbose\nquit\n"), out)
    text = out.getvalue()

    assert "\n\nerror: Premise already exists.\n" in text


def test_repl_interactive_state_renders_empty_state() -> None:
    lines = _run_interactive_lines("clear state\nquit\n")
    assert _contains_subsequence(lines, ["updated", "premise: (none)", "policies: (none)"])


def test_repl_interactive_state_renders_premise_only() -> None:
    lines = _run_interactive_lines("set premise concise\nquit\n")
    assert _contains_subsequence(lines, ["updated", "premise: concise", "policies: (none)"])


def test_repl_interactive_state_renders_policies_only() -> None:
    lines = _run_interactive_lines("use docker\nquit\n")
    assert _contains_subsequence(lines, ["updated", "premise: (none)", "policies:", "- use docker"])


def test_repl_interactive_state_renders_mixed_with_sorted_policies() -> None:
    lines = _run_interactive_lines(
        "set premise concise\nuse docker\nprohibit poetry\nprohibit apples\nquit\n"
    )
    assert _contains_subsequence(
        lines,
        [
            "updated",
            "premise: concise",
            "policies:",
            "- prohibit apples",
            "- use docker",
            "- prohibit poetry",
        ],
    )
