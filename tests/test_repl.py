import json
import pathlib
import subprocess
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


def _run_repl_cli(*args: str, input_text: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "context_compiler.repl", *args],
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def test_main_help_flag_prints_usage_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["context-compiler", "--help"])

    result = repl_module.main()
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == (
        "Usage:\n"
        "  context-compiler [--help] [--version] [--json]\n"
        "                   [--initial-state-json <json> | --initial-state-file <path>]\n"
        "                   [--initial-checkpoint-json <json> | --initial-checkpoint-file <path>]\n"
        "\n"
        "Options:\n"
        "  --help                Show this help message and exit.\n"
        "  --version             Show the installed context-compiler version and exit.\n"
        "  --json                Emit machine-readable NDJSON output (non-interactive only)\n"
        "  --initial-state-json  Initialize authoritative state from exported state JSON text\n"
        "  --initial-state-file  Initialize authoritative state from UTF-8 state JSON file\n"
        "  --initial-checkpoint-json\n"
        "                        Restore runtime continuation from checkpoint JSON text\n"
        "  --initial-checkpoint-file\n"
        "                        Restore runtime continuation from UTF-8 checkpoint JSON file\n"
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
        in_stream: TextIO,
        out_stream: TextIO,
        *,
        json_mode: bool = False,
        engine: object | None = None,
    ) -> None:
        called["in_stream"] = in_stream
        called["out_stream"] = out_stream
        called["json_mode"] = json_mode
        called["engine"] = engine

    monkeypatch.setattr(repl_module, "run_repl", _fake_run_repl)
    monkeypatch.setattr(sys, "argv", ["context-compiler"])

    result = repl_module.main()

    assert result == 0
    assert called["in_stream"] is sys.stdin
    assert called["out_stream"] is sys.stdout
    assert called["json_mode"] is False
    assert called["engine"] is None


def test_main_with_json_flag_runs_repl_with_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    def _fake_run_repl(
        in_stream: TextIO,
        out_stream: TextIO,
        *,
        json_mode: bool = False,
        engine: object | None = None,
    ) -> None:
        called["in_stream"] = in_stream
        called["out_stream"] = out_stream
        called["json_mode"] = json_mode

    monkeypatch.setattr(repl_module, "run_repl", _fake_run_repl)
    monkeypatch.setattr(repl_module, "_is_interactive", lambda _in, _out: False)
    monkeypatch.setattr(sys, "argv", ["context-compiler", "--json"])

    result = repl_module.main()

    assert result == 0
    assert called["in_stream"] is sys.stdin
    assert called["out_stream"] is sys.stdout
    assert called["json_mode"] is True


def test_main_json_requires_non_interactive_stdio(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(repl_module, "_is_interactive", lambda _in, _out: True)
    monkeypatch.setattr(sys, "argv", ["context-compiler", "--json"])

    result = repl_module.main()
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == "error: --json requires non-interactive stdin/stdout.\n"


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


@pytest.mark.parametrize("args", [["--help", "--version"], ["--version", "--json"]])
def test_cli_rejects_non_single_flag_argument_forms(args: list[str]) -> None:
    result = _run_repl_cli(*args)

    assert result.returncode != 0
    assert result.stdout == ""
    assert "error: unknown option" in result.stderr
    assert "Try 'context-compiler --help' for usage." in result.stderr


def test_cli_rejects_unknown_positional_after_flag() -> None:
    result = _run_repl_cli("--json", "foo")
    assert result.returncode != 0
    assert result.stdout == ""
    assert (
        result.stderr == "error: unknown option 'foo'\nTry 'context-compiler --help' for usage.\n"
    )


def test_cli_initial_state_json_preload_works() -> None:
    engine = create_engine()
    engine.step("set premise concise")
    payload = engine.export_json()

    result = _run_repl_cli("--initial-state-json", payload, input_text="state\nquit\n")
    assert result.returncode == 0
    assert "premise: concise" in result.stdout
    assert result.stderr == ""


def test_cli_initial_state_file_preload_works(tmp_path: pathlib.Path) -> None:
    engine = create_engine()
    engine.step("use docker")
    path = tmp_path / "state.json"
    path.write_text(engine.export_json(), encoding="utf-8")

    result = _run_repl_cli("--initial-state-file", str(path), input_text="state\nquit\n")
    assert result.returncode == 0
    assert "policies:" in result.stdout
    assert "- use docker" in result.stdout
    assert result.stderr == ""


def test_cli_initial_checkpoint_json_preload_works_with_pending_confirmation() -> None:
    engine = create_engine()
    engine.step("use kubectl instead of docker")
    payload = engine.export_checkpoint_json()

    result = _run_repl_cli("--initial-checkpoint-json", payload, input_text="yes\nquit\n")
    assert result.returncode == 0
    assert "updated" in result.stdout
    assert "- use kubectl" in result.stdout
    assert result.stderr == ""


def test_cli_initial_checkpoint_file_preload_works(tmp_path: pathlib.Path) -> None:
    engine = create_engine()
    engine.step("set premise concise")
    checkpoint = engine.export_checkpoint_json()
    path = tmp_path / "checkpoint.json"
    path.write_text(checkpoint, encoding="utf-8")

    result = _run_repl_cli("--initial-checkpoint-file", str(path), input_text="state\nquit\n")
    assert result.returncode == 0
    assert "premise: concise" in result.stdout
    assert result.stderr == ""


def test_cli_invalid_initial_state_preload_fails_fast() -> None:
    result = _run_repl_cli("--initial-state-json", '{"bad":true}', input_text="state\nquit\n")
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "error: preload failed: Invalid state payload.\n"


def test_cli_invalid_initial_checkpoint_preload_fails_fast() -> None:
    result = _run_repl_cli("--initial-checkpoint-json", '{"bad":true}', input_text="state\nquit\n")
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "error: preload failed: Invalid checkpoint payload.\n"


def test_cli_preload_mutual_exclusion_state_json_vs_file() -> None:
    result = _run_repl_cli("--initial-state-json", "{}", "--initial-state-file", "/tmp/ignored")
    assert result.returncode == 1
    assert result.stdout == ""
    expected = (
        "error: state preload options are mutually exclusive\n"
        "Try 'context-compiler --help' for usage.\n"
    )
    assert result.stderr == expected


def test_cli_preload_mutual_exclusion_checkpoint_json_vs_file() -> None:
    result = _run_repl_cli(
        "--initial-checkpoint-json", "{}", "--initial-checkpoint-file", "/tmp/ignored"
    )
    assert result.returncode == 1
    assert result.stdout == ""
    expected = (
        "error: checkpoint preload options are mutually exclusive\n"
        "Try 'context-compiler --help' for usage.\n"
    )
    assert result.stderr == expected


def test_cli_preload_mutual_exclusion_state_vs_checkpoint() -> None:
    result = _run_repl_cli("--initial-state-json", "{}", "--initial-checkpoint-json", "{}")
    assert result.returncode == 1
    assert result.stdout == ""
    expected = (
        "error: state preload and checkpoint preload are mutually exclusive\n"
        "Try 'context-compiler --help' for usage.\n"
    )
    assert result.stderr == expected


def test_cli_preload_works_with_json_mode() -> None:
    engine = create_engine()
    engine.step("set premise concise")
    payload = engine.export_json()

    result = _run_repl_cli("--json", "--initial-state-json", payload, input_text="state\nquit\n")
    assert result.returncode == 0
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert lines[0]["mode"] == "state"
    assert lines[0]["state"]["premise"] == "concise"
    assert result.stderr == ""


def test_cli_preload_missing_value_errors() -> None:
    result = _run_repl_cli("--initial-state-json")
    assert result.returncode == 1
    assert result.stdout == ""
    expected = (
        "error: option '--initial-state-json' requires a value\n"
        "Try 'context-compiler --help' for usage.\n"
    )
    assert result.stderr == expected


def test_cli_initial_state_file_preload_unreadable_file_error_is_deterministic(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _boom(_path: str) -> str:
        raise OSError("cannot read preload file")

    monkeypatch.setattr(repl_module, "_read_utf8_file", _boom)
    monkeypatch.setattr(
        sys, "argv", ["context-compiler", "--initial-state-file", "/tmp/state.json"]
    )

    result = repl_module.main()
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == "error: preload failed: cannot read preload file\n"


def test_cli_initial_checkpoint_file_preload_permission_failure_is_deterministic(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _boom(_path: str) -> str:
        raise PermissionError("permission denied")

    monkeypatch.setattr(repl_module, "_read_utf8_file", _boom)
    monkeypatch.setattr(
        sys,
        "argv",
        ["context-compiler", "--initial-checkpoint-file", "/tmp/checkpoint.json"],
    )

    result = repl_module.main()
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == "error: preload failed: permission denied\n"


def test_cli_initial_state_file_preload_utf8_decode_failure_is_deterministic(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _boom(_path: str) -> str:
        raise UnicodeDecodeError("utf-8", b"\x80", 0, 1, "invalid start byte")

    monkeypatch.setattr(repl_module, "_read_utf8_file", _boom)
    monkeypatch.setattr(
        sys, "argv", ["context-compiler", "--initial-state-file", "/tmp/state.json"]
    )

    result = repl_module.main()
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    expected = (
        "error: preload failed: 'utf-8' codec can't decode byte 0x80 in position 0: "
        "invalid start byte\n"
    )
    assert captured.err == expected


def test_parse_cli_options_duplicate_value_flag_rejected() -> None:
    options, error = repl_module._parse_cli_options(
        ["--initial-state-json", "{}", "--initial-state-json", "{}"]
    )
    assert options == {}
    assert error == "option '--initial-state-json' was provided more than once"


def test_parse_cli_options_missing_value_rejected() -> None:
    options, error = repl_module._parse_cli_options(["--initial-state-json"])
    assert options == {}
    assert error == "option '--initial-state-json' requires a value"


def test_parse_cli_options_mutual_exclusion_errors() -> None:
    options_state, error_state = repl_module._parse_cli_options(
        ["--initial-state-json", "{}", "--initial-state-file", "/tmp/x"]
    )
    assert options_state == {}
    assert error_state == "state preload options are mutually exclusive"

    options_ckpt, error_ckpt = repl_module._parse_cli_options(
        ["--initial-checkpoint-json", "{}", "--initial-checkpoint-file", "/tmp/x"]
    )
    assert options_ckpt == {}
    assert error_ckpt == "checkpoint preload options are mutually exclusive"

    options_cross, error_cross = repl_module._parse_cli_options(
        ["--initial-state-json", "{}", "--initial-checkpoint-json", "{}"]
    )
    assert options_cross == {}
    assert error_cross == "state preload and checkpoint preload are mutually exclusive"


def test_apply_preload_from_options_state_and_checkpoint_file_paths(
    tmp_path: pathlib.Path,
) -> None:
    baseline = create_engine()
    baseline.step("set premise concise")
    baseline_checkpoint_engine = create_engine()
    baseline_checkpoint_engine.step("use kubectl instead of docker")

    state_path = tmp_path / "initial_state.json"
    checkpoint_path = tmp_path / "initial_checkpoint.json"
    state_path.write_text(baseline.export_json(), encoding="utf-8")
    checkpoint_path.write_text(
        baseline_checkpoint_engine.export_checkpoint_json(), encoding="utf-8"
    )

    state_engine = create_engine()
    repl_module._apply_preload_from_options(
        state_engine,
        {"json_mode": False, "initial_state_file": str(state_path)},
    )
    assert state_engine.state["premise"] == "concise"

    checkpoint_engine = create_engine()
    repl_module._apply_preload_from_options(
        checkpoint_engine,
        {
            "json_mode": False,
            "initial_checkpoint_file": str(checkpoint_path),
        },
    )
    decision = checkpoint_engine.step("yes")
    assert decision["kind"] == "update"
    assert checkpoint_engine.state["policies"] == {"kubectl": "use"}


def test_apply_preload_from_options_state_and_checkpoint_json() -> None:
    source_state = create_engine()
    source_state.step("set premise concise")
    source_checkpoint = create_engine()
    source_checkpoint.step("use kubectl instead of docker")

    state_engine = create_engine()
    repl_module._apply_preload_from_options(
        state_engine,
        {
            "json_mode": False,
            "initial_state_json": source_state.export_json(),
        },
    )
    assert state_engine.state["premise"] == "concise"

    checkpoint_engine = create_engine()
    repl_module._apply_preload_from_options(
        checkpoint_engine,
        {
            "json_mode": False,
            "initial_checkpoint_json": source_checkpoint.export_checkpoint_json(),
        },
    )
    decision = checkpoint_engine.step("yes")
    assert decision["kind"] == "update"
    assert checkpoint_engine.state["policies"] == {"kubectl": "use"}


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
        "REPL command layer (not engine directives):",
        "  state",
        "  preview <input>",
        "  step <input>     (explicit alias of bare input behavior)",
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
        "Bare input behavior remains unchanged.",
        "preview is a deterministic dry-run and never mutates live state.",
        "Only question prompts accept yes/no confirmations",
        "Other clarify prompts are errors and do not accept yes/no",
    ]
    assert lines[0] == "Context Compiler REPL (0.5). Type help for commands."
    assert lines[1] == "Non-directive input is passthrough."
    expected_help_len = len(expected_help)
    assert lines[2 : 2 + expected_help_len] == expected_help
    assert lines[2 + expected_help_len : 2 + (2 * expected_help_len)] == expected_help


def test_repl_non_interactive_uses_human_readable_output() -> None:
    out = StringIO()
    run_repl(StringIO("hello\nquit\n"), out)

    lines = out.getvalue().splitlines()
    assert lines == ["passthrough"]


def _run_non_interactive_json_lines(text: str) -> list[dict[str, object]]:
    out = StringIO()
    run_repl(StringIO(text), out, json_mode=True)
    return [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]


def test_repl_non_interactive_json_bare_input_step_result() -> None:
    rows = _run_non_interactive_json_lines("set premise concise\nquit\n")
    assert len(rows) == 1
    row = rows[0]
    assert row["output_version"] == 1
    assert row["mode"] == "step"
    assert row["command"] == "input"
    decision = row["decision"]
    assert isinstance(decision, dict)
    assert decision["kind"] == "update"


def test_repl_non_interactive_json_step_and_preview_results() -> None:
    rows = _run_non_interactive_json_lines(
        "step set premise concise\npreview clear premise\nquit\n"
    )
    assert [row["mode"] for row in rows] == ["step", "preview"]
    assert [row["command"] for row in rows] == ["step", "preview"]
    assert rows[0]["output_version"] == 1
    assert rows[1]["output_version"] == 1
    assert "would_mutate" in rows[1]
    assert "diff" in rows[1]


def test_repl_non_interactive_json_state_command() -> None:
    rows = _run_non_interactive_json_lines("set premise concise\nstate\nquit\n")
    assert rows[1]["command"] == "state"
    assert rows[1]["mode"] == "state"
    assert rows[1]["output_version"] == 1
    state = rows[1]["state"]
    assert isinstance(state, dict)
    assert state["premise"] == "concise"
    assert state["policies"] == {}


def test_repl_non_interactive_json_clarify_and_passthrough() -> None:
    rows = _run_non_interactive_json_lines(
        "prohibit docker\nuse kubectl instead of docker\nyes\nhello\nquit\n"
    )
    assert rows[1]["mode"] == "step"
    assert rows[1]["decision"]["kind"] == "clarify"
    assert rows[3]["mode"] == "step"
    assert rows[3]["decision"]["kind"] == "passthrough"


def test_repl_non_interactive_json_machine_readable_errors() -> None:
    rows = _run_non_interactive_json_lines("preview\nstep\nquit\n")
    assert rows == [
        {
            "command": "preview",
            "error": {
                "code": "missing_preview_input",
                "message": "preview requires input.\nUse 'preview <input>'.",
            },
            "mode": "error",
            "output_version": 1,
        },
        {
            "command": "step",
            "error": {
                "code": "missing_step_input",
                "message": "step requires input.\nUse 'step <input>'.",
            },
            "mode": "error",
            "output_version": 1,
        },
    ]


def test_repl_non_interactive_json_multi_command_chunk_error() -> None:
    out = StringIO()
    run_repl(
        _ChunkedInput(["set premise concise\nprohibit peanuts\n", "quit\n"]),  # type: ignore[arg-type]
        out,
        json_mode=True,
    )
    rows = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
    assert rows == [
        {
            "command": "input",
            "error": {
                "code": "multi_command_input",
                "message": "Multiple commands detected.\nEnter one command per line.",
            },
            "mode": "error",
            "output_version": 1,
        }
    ]


def test_repl_non_interactive_json_step_pending_confirmation_error() -> None:
    rows = _run_non_interactive_json_lines(
        "use kubectl instead of docker\nstep set premise concise\nyes\nquit\n"
    )
    assert rows[1] == {
        "command": "step",
        "error": {
            "code": "pending_confirmation_required",
            "message": (
                "step command only accepts confirmation while clarification is pending.\n"
                "Use yes/no (or variants), or use preview/state."
            ),
        },
        "mode": "error",
        "output_version": 1,
    }


def test_repl_non_interactive_json_has_no_human_output_leakage() -> None:
    out = StringIO()
    run_repl(
        StringIO("state\nset premise concise\npreview clear premise\nquit\n"), out, json_mode=True
    )
    for line in out.getvalue().splitlines():
        parsed = json.loads(line)
        assert isinstance(parsed, dict)


def test_repl_non_interactive_state_command_renders_current_state() -> None:
    out = StringIO()
    run_repl(StringIO("set premise concise\nstate\nquit\n"), out)

    lines = out.getvalue().splitlines()
    assert _contains_subsequence(lines, ["updated", "premise: concise", "policies: (none)"])
    assert _contains_subsequence(lines, ["premise: concise", "policies: (none)"])


def test_repl_non_interactive_preview_reports_no_mutation_for_clarify_and_keeps_pending() -> None:
    out = StringIO()
    run_repl(
        StringIO("use kubectl instead of docker\npreview yes\nyes\nquit\n"),
        out,
    )
    lines = [line for line in out.getvalue().splitlines() if line.strip()]

    assert _contains_subsequence(lines, ['confirm: Did you mean to use "kubectl" instead?'])
    assert _contains_subsequence(
        lines, ["preview", "updated", "premise: (none)", "policies:", "- use kubectl"]
    )
    assert _contains_subsequence(lines, ["would_mutate: yes"])
    assert _contains_subsequence(
        lines, ["updated", "premise: (none)", "policies:", "- use kubectl"]
    )


def test_repl_non_interactive_preview_decline_reports_no_mutation() -> None:
    out = StringIO()
    run_repl(StringIO("use kubectl instead of docker\npreview no\nquit\n"), out)
    lines = [line for line in out.getvalue().splitlines() if line.strip()]

    assert _contains_subsequence(
        lines, ["preview", "updated", "premise: (none)", "policies: (none)"]
    )
    assert _contains_subsequence(lines, ["would_mutate: no", "diff:", "- (none)"])


def test_repl_non_interactive_step_alias_matches_bare_input_behavior() -> None:
    bare = _run_non_interactive_lines("set premise concise\nquit\n")
    aliased = _run_non_interactive_lines("step set premise concise\nquit\n")
    assert bare == aliased


def test_repl_non_interactive_preview_and_step_require_payload() -> None:
    out = StringIO()
    run_repl(StringIO("preview\nstep\nquit\n"), out)
    lines = [line for line in out.getvalue().splitlines() if line.strip()]

    assert _contains_subsequence(
        lines, ["error: preview requires input.", "Use 'preview <input>'."]
    )
    assert _contains_subsequence(lines, ["error: step requires input.", "Use 'step <input>'."])


def test_repl_state_command_available_while_pending_clarification() -> None:
    out = StringIO()
    run_repl(StringIO("use kubectl instead of docker\nstate\nyes\nquit\n"), out)
    lines = [line for line in out.getvalue().splitlines() if line.strip()]

    assert _contains_subsequence(lines, ['confirm: Did you mean to use "kubectl" instead?'])
    assert _contains_subsequence(lines, ["premise: (none)", "policies: (none)"])
    assert _contains_subsequence(
        lines, ["updated", "premise: (none)", "policies:", "- use kubectl"]
    )


def test_repl_step_command_rejects_non_confirmation_while_pending() -> None:
    out = StringIO()
    run_repl(
        StringIO("use kubectl instead of docker\nstep set premise concise\nyes\nquit\n"),
        out,
    )
    lines = [line for line in out.getvalue().splitlines() if line.strip()]

    assert _contains_subsequence(lines, ['confirm: Did you mean to use "kubectl" instead?'])
    assert _contains_subsequence(
        lines,
        [
            "error: step command only accepts confirmation while clarification is pending.",
            "Use yes/no (or variants), or use preview/state.",
        ],
    )
    assert _contains_subsequence(
        lines, ["updated", "premise: (none)", "policies:", "- use kubectl"]
    )


def test_repl_step_command_accepts_confirmation_while_pending() -> None:
    out = StringIO()
    run_repl(StringIO("use kubectl instead of docker\nstep yes\nquit\n"), out)
    lines = [line for line in out.getvalue().splitlines() if line.strip()]

    assert _contains_subsequence(lines, ['confirm: Did you mean to use "kubectl" instead?'])
    assert _contains_subsequence(
        lines, ["updated", "premise: (none)", "policies:", "- use kubectl"]
    )


def test_repl_step_command_accepts_negative_confirmation_while_pending() -> None:
    out = StringIO()
    run_repl(StringIO("use kubectl instead of docker\nstep no\nquit\n"), out)
    lines = [line for line in out.getvalue().splitlines() if line.strip()]

    assert _contains_subsequence(lines, ['confirm: Did you mean to use "kubectl" instead?'])
    assert _contains_subsequence(lines, ["updated", "premise: (none)", "policies: (none)"])


def test_repl_preview_available_while_pending_clarification() -> None:
    out = StringIO()
    run_repl(StringIO("use kubectl instead of docker\npreview yes\nyes\nquit\n"), out)
    lines = [line for line in out.getvalue().splitlines() if line.strip()]

    assert _contains_subsequence(
        lines, ["preview", "updated", "premise: (none)", "policies:", "- use kubectl"]
    )


def test_repl_interactive_preview_available_while_pending_clarification() -> None:
    lines = _run_interactive_lines("use kubectl instead of docker\npreview yes\nyes\nquit\n")

    assert _contains_subsequence(lines, ['confirm: Did you mean to use "kubectl" instead?'])
    assert _contains_subsequence(
        lines, ["preview", "updated", "premise: (none)", "policies:", "- use kubectl"]
    )
    assert _contains_subsequence(lines, ["would_mutate: yes"])
    assert _contains_subsequence(
        lines, ["updated", "premise: (none)", "policies:", "- use kubectl"]
    )


def test_repl_interactive_help_available_while_pending_clarification() -> None:
    lines = _run_interactive_lines("use kubectl instead of docker\nhelp\nyes\nquit\n")

    assert _contains_subsequence(lines, ['confirm: Did you mean to use "kubectl" instead?'])
    assert _contains_subsequence(lines, ["Commands: help/? exit/quit"])
    assert _contains_subsequence(lines, ["REPL command layer (not engine directives):"])
    assert _contains_subsequence(
        lines, ["updated", "premise: (none)", "policies:", "- use kubectl"]
    )


def test_repl_preview_idempotent_admin_action_reports_no_mutation() -> None:
    out = StringIO()
    run_repl(StringIO("preview clear premise\nquit\n"), out)
    lines = [line for line in out.getvalue().splitlines() if line.strip()]

    assert _contains_subsequence(
        lines, ["preview", "updated", "premise: (none)", "policies: (none)"]
    )
    assert _contains_subsequence(lines, ["would_mutate: no", "diff:", "- (none)"])


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


def test_repl_interactive_state_command_renders_current_state() -> None:
    lines = _run_interactive_lines("state\nquit\n")
    assert _contains_subsequence(lines, ["premise: (none)", "policies: (none)"])


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


def test_repl_interactive_step_command_paths_while_pending() -> None:
    lines = _run_interactive_lines("use kubectl instead of docker\nstep maybe\nstep yes!!!\nquit\n")

    assert _contains_subsequence(lines, ['confirm: Did you mean to use "kubectl" instead?'])
    assert _contains_subsequence(
        lines,
        [
            "error: step command only accepts confirmation while clarification is pending.",
            "Use yes/no (or variants), or use preview/state.",
        ],
    )
    assert _contains_subsequence(
        lines, ["updated", "premise: (none)", "policies:", "- use kubectl"]
    )


def test_repl_interactive_preview_requires_payload() -> None:
    lines = _run_interactive_lines("preview\nquit\n")
    assert _contains_subsequence(
        lines, ["error: preview requires input.", "Use 'preview <input>'."]
    )


def test_repl_interactive_step_requires_payload() -> None:
    lines = _run_interactive_lines("step\nquit\n")
    assert _contains_subsequence(lines, ["error: step requires input.", "Use 'step <input>'."])


def test_repl_interactive_preview_renders_structural_diff_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview_result = {
        "output_version": 1,
        "mode": "preview",
        "decision": {
            "kind": "update",
            "state": {"premise": "after", "policies": {"docker": "prohibit"}},
            "prompt_to_user": None,
        },
        "state_before": {"premise": "before", "policies": {"docker": "use", "kubectl": "use"}},
        "state_after": {"premise": "after", "policies": {"docker": "prohibit"}},
        "diff": {
            "changed": True,
            "premise": {"before": "before", "after": "after", "changed": True},
            "policies": {
                "added": {},
                "removed": {"kubectl": "use"},
                "changed": {"docker": {"before": "use", "after": "prohibit"}},
            },
        },
        "would_mutate": True,
    }

    def _fake_preview(_engine: object, _user_input: str) -> object:
        return preview_result

    monkeypatch.setattr(repl_module, "controller_preview", _fake_preview)

    lines = _run_interactive_lines("preview test\nquit\n")
    assert _contains_subsequence(lines, ["preview", "updated"])
    assert _contains_subsequence(lines, ["- premise: before -> after"])
    assert _contains_subsequence(lines, ["- - use kubectl"])
    assert _contains_subsequence(lines, ["- ~ use docker -> prohibit docker"])
