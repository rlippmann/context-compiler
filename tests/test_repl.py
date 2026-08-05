import json
import pathlib
import subprocess
import sys
from io import StringIO
from typing import TextIO

import pytest

import context_compiler.repl as repl_module
from context_compiler import DECISION_UPDATE, __version__, create_engine
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


def _run_non_interactive_json_lines(text: str) -> list[dict[str, object]]:
    out = StringIO()
    run_repl(StringIO(text), out, json_mode=True)
    return [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]


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
        "\n"
        "Options:\n"
        "  --help                Show this help message and exit.\n"
        "  --version             Show the installed context-compiler version and exit.\n"
        "  --json                Emit machine-readable NDJSON output (non-interactive only)\n"
        "  --initial-state-json  Initialize authoritative state from exported state JSON text\n"
        "  --initial-state-file  Initialize authoritative state from UTF-8 state JSON file\n"
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


def test_cli_invalid_initial_state_preload_fails_fast() -> None:
    result = _run_repl_cli("--initial-state-json", '{"bad":true}', input_text="state\nquit\n")
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "error: preload failed: Invalid state payload.\n"


def test_repl_update_flow() -> None:
    lines = _run_non_interactive_lines("set premise concise\nquit\n")
    assert lines == ["updated", "premise: concise", "policies: (none)"]


def test_repl_step_alias_matches_bare_input_behavior() -> None:
    bare = _run_non_interactive_lines("set premise concise\nquit\n")
    aliased = _run_non_interactive_lines("step set premise concise\nquit\n")
    assert bare == aliased


def test_repl_step_requires_payload() -> None:
    lines = _run_non_interactive_lines("step\nquit\n")
    assert _contains_subsequence(lines, ["error: step requires input.", "Use 'step <input>'."])


def test_repl_state_command_renders_current_state() -> None:
    lines = _run_non_interactive_lines("set premise concise\nstate\nquit\n")
    assert _contains_subsequence(lines, ["updated", "premise: concise", "policies: (none)"])
    assert _contains_subsequence(lines, ["premise: concise", "policies: (none)"])


def test_repl_non_interactive_json_bare_input_step_result() -> None:
    rows = _run_non_interactive_json_lines("set premise concise\nquit\n")
    assert len(rows) == 1
    row = rows[0]
    assert row["output_version"] == 1
    assert row["mode"] == "step"
    assert row["command"] == "input"
    assert row["state"] == {"premise": "concise", "policies": {}, "version": 2}
    decision = row["decision"]
    assert isinstance(decision, dict)
    assert decision["kind"] == DECISION_UPDATE


def test_repl_non_interactive_json_state_command() -> None:
    rows = _run_non_interactive_json_lines("set premise concise\nstate\nquit\n")
    assert rows[1]["command"] == "state"
    assert rows[1]["mode"] == "state"
    assert rows[1]["output_version"] == 1
    state = rows[1]["state"]
    assert isinstance(state, dict)
    assert state["premise"] == "concise"
    assert state["policies"] == {}


def test_repl_non_interactive_json_machine_readable_step_error() -> None:
    rows = _run_non_interactive_json_lines("step\nquit\n")
    assert rows == [
        {
            "command": "step",
            "error": {
                "code": "missing_step_input",
                "message": "step requires input.\nUse 'step <input>'.",
            },
            "mode": "error",
            "output_version": 1,
        }
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


def test_repl_interactive_help_commands() -> None:
    out = _TTYStringIO()
    run_repl(_TTYStringIO("help\n?\nquit\n"), out)

    lines = out.getvalue().splitlines()
    expected_help = [
        "Commands: help/? exit/quit",
        "REPL command layer (not engine directives):",
        "  state",
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
        "error results are immediate messages and do not reserve later input.",
    ]
    assert lines[0] == "Context Compiler REPL (0.5). Type help for commands."
    assert lines[1] == "Non-directive input is no_directive."
    expected_help_len = len(expected_help)
    assert lines[2 : 2 + expected_help_len] == expected_help
    assert lines[2 + expected_help_len : 2 + (2 * expected_help_len)] == expected_help


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


def test_repl_interactive_blank_line_is_ignored_without_output() -> None:
    lines = _run_interactive_lines("\nset premise concise\nquit\n")
    assert lines[0] == "Context Compiler REPL (0.5). Type help for commands."
    assert lines[1] == "Non-directive input is no_directive."
    assert _contains_subsequence(lines, ["updated", "premise: concise", "policies: (none)"])
