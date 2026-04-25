import sys
from io import StringIO
from typing import TextIO

import pytest

import context_compiler.repl as repl_module
from context_compiler import __version__, create_engine
from context_compiler.repl import run_repl

pytestmark = pytest.mark.contract


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


def test_main_help_flag_prints_usage_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["context-compiler", "--help"])

    result = repl_module.main()
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == (
        "Usage:\n"
        "  context-compiler [--help] [--version] [--with-precompiler]\n"
        "\n"
        "Options:\n"
        "  --help               Show this help message and exit.\n"
        "  --version            Show the installed context-compiler version and exit.\n"
        "  --with-precompiler   Enable heuristic precompiler validation in the REPL loop.\n"
    )
    assert captured.err == ""


def test_main_version_flag_prints_installed_version_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["context-compiler", "--version"])

    result = repl_module.main()
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == f"{__version__}\n"
    assert captured.err == ""


def test_main_without_args_runs_repl_as_before(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    def _fake_run_repl(
        in_stream: TextIO, out_stream: TextIO, *, use_precompiler: bool = False
    ) -> None:
        called["in_stream"] = in_stream
        called["out_stream"] = out_stream
        called["use_precompiler"] = use_precompiler

    monkeypatch.setattr(repl_module, "run_repl", _fake_run_repl)
    monkeypatch.setattr(sys, "argv", ["context-compiler"])

    result = repl_module.main()

    assert result == 0
    assert called["in_stream"] is sys.stdin
    assert called["out_stream"] is sys.stdout
    assert called["use_precompiler"] is False


def test_main_with_precompiler_flag_runs_repl_with_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    def _fake_run_repl(
        in_stream: TextIO, out_stream: TextIO, *, use_precompiler: bool = False
    ) -> None:
        called["in_stream"] = in_stream
        called["out_stream"] = out_stream
        called["use_precompiler"] = use_precompiler

    monkeypatch.setattr(repl_module, "run_repl", _fake_run_repl)
    monkeypatch.setattr(sys, "argv", ["context-compiler", "--with-precompiler"])

    result = repl_module.main()

    assert result == 0
    assert called["in_stream"] is sys.stdin
    assert called["out_stream"] is sys.stdout
    assert called["use_precompiler"] is True


def test_main_unknown_flag_prints_error_hint_and_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["context-compiler", "--bogus"])

    result = repl_module.main()
    captured = capsys.readouterr()

    assert result != 0
    assert captured.out == ""
    assert captured.err == (
        "error: unknown option '--bogus'\nTry 'context-compiler --help' for usage.\n"
    )


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


def test_repl_with_precompiler_parses_directive_before_engine_step() -> None:
    out = StringIO()
    run_repl(
        StringIO('{"classification":"directive","output":"prohibit peanuts"}\nquit\n'),
        out,
        use_precompiler=True,
    )

    lines = out.getvalue().splitlines()
    assert lines == ["updated", "premise: (none)", "policies:", "- prohibit peanuts"]


def test_repl_with_precompiler_near_miss_passes_through_and_clarifies() -> None:
    out = StringIO()
    run_repl(StringIO("set premise to concise replies\nquit\n"), out, use_precompiler=True)

    lines = out.getvalue().splitlines()
    assert lines == ["confirm: Did you mean 'set premise concise replies'?"]


def test_repl_with_precompiler_non_directive_passthrough() -> None:
    out = StringIO()
    run_repl(StringIO("what is a simple curry recipe?\nquit\n"), out, use_precompiler=True)

    lines = out.getvalue().splitlines()
    assert lines == ["passthrough"]


def test_repl_with_precompiler_bypasses_parsing_while_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[object, str | None]] = []

    def _parse(raw_output: object, *, source_input: str | None = None) -> str | None:
        seen.append((raw_output, source_input))
        if raw_output == "use podman instead of docker":
            return "use podman instead of docker"
        raise AssertionError("parse_precompiler_output should be bypassed while pending")

    monkeypatch.setattr(repl_module, "parse_precompiler_output", _parse)

    out = StringIO()
    run_repl(
        StringIO("use podman instead of docker\nyes\nquit\n"),
        out,
        use_precompiler=True,
    )

    assert seen == [("use podman instead of docker", "use podman instead of docker")]
    lines = out.getvalue().splitlines()
    assert _contains_subsequence(lines, ['confirm: Did you mean to use "podman" instead?'])
    assert _contains_subsequence(lines, ["updated", "premise: (none)", "policies:", "- use podman"])


def test_repl_without_precompiler_does_not_parse_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail_parse(_raw: object, *, source_input: str | None = None) -> str | None:
        del source_input
        raise AssertionError("parse_precompiler_output should not be called")

    monkeypatch.setattr(repl_module, "parse_precompiler_output", _fail_parse)

    out = StringIO()
    run_repl(StringIO('{"classification":"directive","output":"prohibit peanuts"}\nquit\n'), out)

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


def test_repl_non_interactive_rejects_embedded_carriage_return_multi_command_chunk() -> None:
    out = StringIO()
    run_repl(
        _ChunkedInput(["set premise concise\rprohibit peanuts\n", "quit\n"]),  # type: ignore[arg-type]
        out,
    )

    lines = out.getvalue().splitlines()
    assert lines == ["error: Multiple commands detected.", "Enter one command per line."]


def test_repl_non_interactive_accepts_crlf_single_line_without_multi_command_error() -> None:
    out = StringIO()
    run_repl(
        _ChunkedInput(["hello\r\n", "quit\r\n"]),  # type: ignore[arg-type]
        out,
    )

    lines = out.getvalue().splitlines()
    assert lines == ["passthrough"]


def test_repl_interactive_rejects_embedded_carriage_return_multi_command_chunk() -> None:
    out = _TTYStringIO()
    run_repl(
        _ChunkedTTYInput(["set premise concise\rprohibit peanuts\n", "quit\n"]),  # type: ignore[arg-type]
        out,
    )

    lines = out.getvalue().splitlines()
    assert "error: Multiple commands detected." in lines
    assert "Enter one command per line." in lines
    assert "updated" not in lines


def test_repl_invalid_directive_near_misses_remain_passthrough() -> None:
    lines = _run_non_interactive_lines("actually use uv\nno use peanuts\nallow docker\nquit\n")
    assert lines == ["passthrough", "passthrough", "passthrough"]


def test_repl_empty_policy_payloads_and_incomplete_replacement_render_errors() -> None:
    lines = _run_non_interactive_lines(
        "use\nprohibit   \nuse x instead of\nuse instead of y\nquit\n"
    )
    assert _contains_subsequence(
        lines,
        [
            "error: Policy item cannot be empty.",
            "Use 'use <item>' with a non-empty value.",
        ],
    )
    assert _contains_subsequence(
        lines,
        [
            "error: Policy item cannot be empty.",
            "Use 'prohibit <item>' with a non-empty value.",
        ],
    )
    assert lines.count("error: Replacement requires both new and old items.") == 2
    assert lines.count("Use 'use <new item> instead of <old item>' with non-empty values.") == 2


def test_repl_premise_to_variant_near_misses_render_error_suggestions() -> None:
    lines = _run_non_interactive_lines(
        "set premise to concise replies\nchange premise concise replies\nquit\n"
    )
    assert _contains_subsequence(lines, ["confirm: Did you mean 'set premise concise replies'?"])
    assert _contains_subsequence(
        lines, ["confirm: Did you mean 'change premise to concise replies'?"]
    )


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
            'error: "docker" is currently in use.',
            "Remove or replace it before prohibiting it.",
            "passthrough",
        ],
    )


def test_repl_change_premise_without_existing_premise_renders_exact_error() -> None:
    lines = _run_non_interactive_lines("change premise to concise\nquit\n")
    assert _contains_subsequence(
        lines,
        [
            "error: No premise is set.",
            "Use 'set premise <value>' to define one.",
        ],
    )


def test_repl_set_premise_empty_payload_renders_exact_error() -> None:
    lines = _run_non_interactive_lines("set premise\nquit\n")
    assert _contains_subsequence(
        lines,
        [
            "error: Premise value cannot be empty.",
            "Use 'set premise <value>' with a non-empty value.",
        ],
    )


def test_repl_change_premise_empty_payload_renders_exact_error() -> None:
    lines = _run_non_interactive_lines("change premise to\nquit\n")
    assert _contains_subsequence(
        lines,
        [
            "error: Premise value cannot be empty.",
            "Use 'change premise to <value>' with a non-empty value.",
        ],
    )


def test_repl_use_item_when_prohibited_renders_exact_error() -> None:
    lines = _run_non_interactive_lines("prohibit docker\nuse docker\nquit\n")
    assert _contains_subsequence(
        lines,
        [
            'error: "docker" is currently prohibited.',
            "Remove or replace it before using it.",
        ],
    )


def test_repl_replace_use_when_old_policy_not_use_renders_exact_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine()
    engine._state["policies"]["docker"] = "invalid"  # type: ignore[assignment]
    monkeypatch.setattr(repl_module, "create_engine", lambda: engine)

    out = StringIO()
    run_repl(StringIO("use podman instead of docker\nquit\n"), out)
    lines = [line for line in out.getvalue().splitlines() if line.strip()]

    assert _contains_subsequence(
        lines,
        [
            'error: "docker" is not currently in use.',
            "Replacement requires an active 'use' policy.",
        ],
    )


def test_repl_replacement_clarify_requires_confirmation_tokens_and_persists_until_resolved() -> (
    None
):
    lines = _run_non_interactive_lines("use podman instead of docker\nmaybe\nyes please!!\nquit\n")
    assert lines.count('confirm: Did you mean to use "podman" instead?') == 2
    assert _contains_subsequence(lines, ["updated", "premise: (none)", "policies:", "- use podman"])


def test_repl_interactive_prints_confirm_and_error_for_clarify_types() -> None:
    error_out = _TTYStringIO()
    run_repl(_TTYStringIO("use docker\nprohibit docker\nquit\n"), error_out)
    error_lines = error_out.getvalue().splitlines()
    assert 'error: "docker" is currently in use.' in error_lines
    assert "Remove or replace it before prohibiting it." in error_lines

    confirm_out = _TTYStringIO()
    run_repl(_TTYStringIO("use podman instead of docker\nquit\n"), confirm_out)
    confirm_lines = confirm_out.getvalue().splitlines()
    assert 'confirm: Did you mean to use "podman" instead?' in confirm_lines


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
            "error: Premise already set.",
            "Use 'change premise to <value>' to modify it.",
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
    assert 'confirm: Did you mean to use "podman" instead?' in lines_yes
    assert _contains_subsequence(
        lines_yes, ["updated", "premise: (none)", "policies:", "- use podman"]
    )

    lines_ok = _run_interactive_lines("use buildah instead of docker\nok\nquit\n")
    assert 'confirm: Did you mean to use "buildah" instead?' in lines_ok
    assert _contains_subsequence(
        lines_ok, ["updated", "premise: (none)", "policies:", "- use buildah"]
    )

    lines_nope = _run_interactive_lines("use nerdctl instead of docker\nnope\nquit\n")
    assert 'confirm: Did you mean to use "nerdctl" instead?' in lines_nope
    assert _contains_subsequence(lines_nope, ["updated", "premise: (none)", "policies: (none)"])

    lines_no_thanks = _run_interactive_lines("use helm instead of docker\nno thanks\nquit\n")
    assert 'confirm: Did you mean to use "helm" instead?' in lines_no_thanks
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

    assert ("error: Premise already set.") in lines
    assert "Use 'change premise to <value>' to modify it." in lines
    assert ('error: "docker" is currently in use.') in lines
    assert "Remove or replace it before prohibiting it." in lines
    assert 'confirm: Did you mean to use "podman" instead?' in lines


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

    assert "\n\nerror: Premise already set.\n" in text


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
