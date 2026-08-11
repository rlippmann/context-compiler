"""Command-line and REPL entry points for interacting with the engine."""

import json
import sys
from collections.abc import Mapping
from typing import TextIO

from . import __version__
from .const import STATE_POLICIES, STATE_PREMISE, STATE_VERSION
from .decision_helpers import is_error, is_no_directive, is_update
from .engine import Decision, DecisionKind, Engine, PolicyValue

OUTPUT_VERSION = 1

_EXIT_TOKENS = {"exit", "quit"}
_HELP_TOKENS = {"help", "?"}
_MULTI_COMMAND_PROMPT = "Multiple commands detected.\nEnter one command per line."
_CLI_HELP_TEXT = """Usage:
  context-compiler [--help] [--version] [--json]
                   [--initial-state-json <json> | --initial-state-file <path>]

Options:
  --help                Show this help message and exit.
  --version             Show the installed context-compiler version and exit.
  --json                Emit machine-readable NDJSON output (non-interactive only)
  --initial-state-json  Initialize authoritative state from exported state JSON text
  --initial-state-file  Initialize authoritative state from UTF-8 state JSON file
"""


def _is_interactive(in_stream: TextIO, out_stream: TextIO) -> bool:
    return bool(in_stream.isatty() and out_stream.isatty())


def _has_embedded_newline(raw_line: str) -> bool:
    body = raw_line[:-1] if raw_line.endswith("\n") else raw_line
    if body.endswith("\r"):
        body = body[:-1]
    return "\n" in body or "\r" in body


def _multi_command_decision() -> Decision:
    return {"kind": DecisionKind.ERROR, "message": _MULTI_COMMAND_PROMPT}


def _print_interactive_help(out_stream: TextIO) -> None:
    print("Commands: help/? exit/quit", file=out_stream)
    print("REPL command layer (not engine directives):", file=out_stream)
    print("  state", file=out_stream)
    print("  step <input>     (explicit alias of bare input behavior)", file=out_stream)
    print("Directives (exact prefix only):", file=out_stream)
    print("  set premise <value>", file=out_stream)
    print("  change premise to <value>", file=out_stream)
    print("  use <item>", file=out_stream)
    print("  prohibit <item>", file=out_stream)
    print("  remove policy <item>", file=out_stream)
    print("  use <new item> instead of <old item>", file=out_stream)
    print("  clear premise", file=out_stream)
    print("  reset policies", file=out_stream)
    print("  clear state", file=out_stream)
    print("Bare input behavior remains unchanged.", file=out_stream)
    print("error results are immediate messages and do not reserve later input.", file=out_stream)


def _render_state_lines(*, premise: str | None, policies: Mapping[str, PolicyValue]) -> list[str]:
    premise_line = "premise: (none)" if premise is None else f"premise: {premise}"
    if not policies:
        return [premise_line, "policies: (none)"]

    policy_items = sorted(policies.items())

    lines = [premise_line, "policies:"]
    for item, value in policy_items:
        lines.append(f"- {value} {item}")
    return lines


def _render_decision_lines(
    decision: Decision,
    *,
    premise: str | None = None,
    policies: Mapping[str, PolicyValue] | None = None,
) -> list[str]:
    if is_no_directive(decision):
        return ["no_directive"]
    if is_error(decision):
        message = decision["message"]
        prompt_lines = message.splitlines() if message else [""]
        return [f"error: {prompt_lines[0]}", *prompt_lines[1:]]

    assert is_update(decision)
    assert policies is not None
    return ["updated", *_render_state_lines(premise=premise, policies=policies)]


def _print_decision_lines(
    decision: Decision,
    out_stream: TextIO,
    *,
    leading_blank: bool,
    premise: str | None = None,
    policies: Mapping[str, PolicyValue] | None = None,
) -> None:
    if leading_blank:
        print("", file=out_stream)
    for line in _render_decision_lines(decision, premise=premise, policies=policies):
        print(line, file=out_stream)


def _print_command_error(out_stream: TextIO, *, leading_blank: bool, message: str) -> None:
    if leading_blank:
        print("", file=out_stream)
    print(f"error: {message}", file=out_stream)


def _write_json_line(out_stream: TextIO, payload: dict[str, object]) -> None:
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True), file=out_stream)


def _state_payload(
    *, premise: str | None, policies: Mapping[str, PolicyValue]
) -> dict[str, object]:
    return {
        STATE_PREMISE: premise,
        STATE_POLICIES: dict(policies),
        STATE_VERSION: 2,
    }


def _json_step_payload(
    decision: Decision,
    *,
    command: str,
    premise: str | None,
    policies: Mapping[str, PolicyValue],
    mode: str = "step",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "output_version": OUTPUT_VERSION,
        "mode": mode,
        "decision": decision,
        "state": _state_payload(premise=premise, policies=policies),
    }
    payload["command"] = command
    return payload


def _json_state_payload(
    *, premise: str | None, policies: Mapping[str, PolicyValue]
) -> dict[str, object]:
    return {
        "output_version": OUTPUT_VERSION,
        "mode": "state",
        "command": "state",
        "state": _state_payload(premise=premise, policies=policies),
    }


def _json_error_payload(*, command: str, code: str, message: str) -> dict[str, object]:
    return {
        "output_version": OUTPUT_VERSION,
        "mode": "error",
        "command": command,
        "error": {"code": code, "message": message},
    }


def _read_utf8_file(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _parse_cli_options(args: list[str]) -> tuple[dict[str, str | bool], str | None]:
    options: dict[str, str | bool] = {
        "json_mode": False,
    }

    value_flags = {
        "--initial-state-json": "initial_state_json",
        "--initial-state-file": "initial_state_file",
    }

    idx = 0
    while idx < len(args):
        arg = args[idx]
        if arg == "--json":
            options["json_mode"] = True
            idx += 1
            continue
        if arg in value_flags:
            key = value_flags[arg]
            if idx + 1 >= len(args):
                return {}, f"option '{arg}' requires a value"
            if key in options:
                return {}, f"option '{arg}' was provided more than once"
            options[key] = args[idx + 1]
            idx += 2
            continue
        return {}, f"unknown option '{arg}'"

    has_state_json = "initial_state_json" in options
    has_state_file = "initial_state_file" in options

    if has_state_json and has_state_file:
        return {}, "state preload options are mutually exclusive"

    return options, None


def _apply_preload_from_options(engine: Engine, options: dict[str, str | bool]) -> None:
    if "initial_state_json" in options:
        raw = options["initial_state_json"]
        assert isinstance(raw, str)
        engine.import_json(raw)
        return
    if "initial_state_file" in options:
        path = options["initial_state_file"]
        assert isinstance(path, str)
        engine.import_json(_read_utf8_file(path))


def run_repl(
    in_stream: TextIO,
    out_stream: TextIO,
    *,
    json_mode: bool = False,
    engine: Engine | None = None,
) -> None:
    """Run the interactive or line-oriented REPL against one engine instance.

    Interactive mode exposes command helpers such as ``state`` and ``step``.
    Non-interactive mode consumes one input line at a time and can optionally
    emit NDJSON records.
    """

    active_engine = Engine() if engine is None else engine

    if _is_interactive(in_stream, out_stream):
        print("Context Compiler REPL (0.5). Type help for commands.", file=out_stream)
        print("Non-directive input is no_directive.", file=out_stream)

        while True:
            line = in_stream.readline()
            if line == "":
                return
            if _has_embedded_newline(line):
                _print_decision_lines(_multi_command_decision(), out_stream, leading_blank=True)
                continue
            user_input = line.rstrip("\n")
            token = user_input.strip().lower()
            if not token:
                continue
            if token in _EXIT_TOKENS:
                return
            if token in _HELP_TOKENS:
                _print_interactive_help(out_stream)
                continue

            if token == "state":
                print("", file=out_stream)
                for line in _render_state_lines(
                    premise=active_engine.premise,
                    policies=active_engine.policies,
                ):
                    print(line, file=out_stream)
                continue

            if user_input.startswith("step"):
                payload = user_input[4:].lstrip() if user_input != "step" else ""
                if token == "step" and payload == "":
                    _print_command_error(
                        out_stream,
                        leading_blank=True,
                        message="step requires input.\nUse 'step <input>'.",
                    )
                    continue
                if payload != "" and (user_input == "step" or user_input.startswith("step ")):
                    decision = active_engine.step(payload)
                    _print_decision_lines(
                        decision,
                        out_stream,
                        leading_blank=True,
                        premise=active_engine.premise,
                        policies=active_engine.policies,
                    )
                    continue

            decision = active_engine.step(user_input)
            _print_decision_lines(
                decision,
                out_stream,
                leading_blank=True,
                premise=active_engine.premise,
                policies=active_engine.policies,
            )
        return

    for line in in_stream:
        if _has_embedded_newline(line):
            if json_mode:
                _write_json_line(
                    out_stream,
                    _json_error_payload(
                        command="input",
                        code="multi_command_input",
                        message=_MULTI_COMMAND_PROMPT,
                    ),
                )
            else:
                _print_decision_lines(_multi_command_decision(), out_stream, leading_blank=False)
            continue
        user_input = line.rstrip("\n")
        if user_input.strip().lower() in _EXIT_TOKENS:
            return

        token = user_input.strip().lower()
        if token == "state":
            if json_mode:
                _write_json_line(
                    out_stream,
                    _json_state_payload(
                        premise=active_engine.premise,
                        policies=active_engine.policies,
                    ),
                )
            else:
                for state_line in _render_state_lines(
                    premise=active_engine.premise,
                    policies=active_engine.policies,
                ):
                    print(state_line, file=out_stream)
            continue

        if user_input.startswith("step"):
            payload = user_input[4:].lstrip() if user_input != "step" else ""
            if token == "step" and payload == "":
                if json_mode:
                    _write_json_line(
                        out_stream,
                        _json_error_payload(
                            command="step",
                            code="missing_step_input",
                            message="step requires input.\nUse 'step <input>'.",
                        ),
                    )
                else:
                    _print_command_error(
                        out_stream,
                        leading_blank=False,
                        message="step requires input.\nUse 'step <input>'.",
                    )
                continue
            if payload != "" and (user_input == "step" or user_input.startswith("step ")):
                decision = active_engine.step(payload)
                if json_mode:
                    _write_json_line(
                        out_stream,
                        _json_step_payload(
                            decision,
                            command="step",
                            premise=active_engine.premise,
                            policies=active_engine.policies,
                        ),
                    )
                else:
                    _print_decision_lines(
                        decision,
                        out_stream,
                        leading_blank=False,
                        premise=active_engine.premise,
                        policies=active_engine.policies,
                    )
                continue

        decision = active_engine.step(user_input)
        if json_mode:
            _write_json_line(
                out_stream,
                _json_step_payload(
                    decision,
                    command="input",
                    premise=active_engine.premise,
                    policies=active_engine.policies,
                ),
            )
        else:
            _print_decision_lines(
                decision,
                out_stream,
                leading_blank=False,
                premise=active_engine.premise,
                policies=active_engine.policies,
            )


def main() -> int:  # pragma: no cover
    """Run the command-line entry point and return the process exit status."""

    args = sys.argv[1:]
    if not args:
        run_repl(sys.stdin, sys.stdout)
        return 0

    if args == ["--help"]:
        print(_CLI_HELP_TEXT, file=sys.stdout, end="")
        return 0

    if args == ["--version"]:
        print(__version__, file=sys.stdout)
        return 0

    options, parse_error = _parse_cli_options(args)
    if parse_error is not None:
        print(f"error: {parse_error}", file=sys.stderr)
        print("Try 'context-compiler --help' for usage.", file=sys.stderr)
        return 1

    json_mode = bool(options["json_mode"])
    if json_mode and _is_interactive(sys.stdin, sys.stdout):
        print("error: --json requires non-interactive stdin/stdout.", file=sys.stderr)
        return 1

    engine = Engine()
    try:
        _apply_preload_from_options(engine, options)
    except (OSError, ValueError) as exc:
        print(f"error: preload failed: {exc}", file=sys.stderr)
        return 1

    run_repl(sys.stdin, sys.stdout, json_mode=json_mode, engine=engine)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
