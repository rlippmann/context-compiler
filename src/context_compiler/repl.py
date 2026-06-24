import json
import sys
from typing import TextIO

from . import __version__, create_engine, get_policy_items, get_premise_value
from .const import DECISION_CLARIFY, DECISION_PASSTHROUGH
from .controller import (
    OUTPUT_VERSION,
    PreviewResult,
    StepResult,
    get_preview_decision,
    get_step_decision,
    preview_would_mutate,
)
from .controller import preview as controller_preview
from .controller import step as controller_step
from .engine import Decision, DecisionKind, Engine, State

_EXIT_TOKENS = {"exit", "quit"}
_HELP_TOKENS = {"help", "?"}
_MULTI_COMMAND_PROMPT = "Multiple commands detected.\nEnter one command per line."
_AFFIRMATIVE_CONFIRMATIONS = {"yes", "yes please", "yep", "yeah", "sure", "ok", "okay"}
_NEGATIVE_CONFIRMATIONS = {"no", "nope", "no thanks"}
_STEP_PENDING_CONFIRMATION_ERROR = (
    "step command only accepts confirmation while clarification is pending.\n"
    "Use yes/no (or variants), or use preview/state."
)
_CLI_HELP_TEXT = """Usage:
  context-compiler [--help] [--version] [--json]
                   [--initial-state-json <json> | --initial-state-file <path>]
                   [--initial-checkpoint-json <json> | --initial-checkpoint-file <path>]

Options:
  --help                Show this help message and exit.
  --version             Show the installed context-compiler version and exit.
  --json                Emit machine-readable NDJSON output (non-interactive only)
  --initial-state-json  Initialize authoritative state from exported state JSON text
  --initial-state-file  Initialize authoritative state from UTF-8 state JSON file
  --initial-checkpoint-json
                        Restore runtime continuation from checkpoint JSON text
  --initial-checkpoint-file
                        Restore runtime continuation from UTF-8 checkpoint JSON file
"""


def _is_interactive(in_stream: TextIO, out_stream: TextIO) -> bool:
    return bool(in_stream.isatty() and out_stream.isatty())


def _has_embedded_newline(raw_line: str) -> bool:
    body = raw_line[:-1] if raw_line.endswith("\n") else raw_line
    if body.endswith("\r"):
        body = body[:-1]
    return "\n" in body or "\r" in body


def _multi_command_decision() -> Decision:
    return {
        "kind": DecisionKind.CLARIFY,
        "state": None,
        "prompt_to_user": _MULTI_COMMAND_PROMPT,
    }


def _print_interactive_help(out_stream: TextIO) -> None:
    print("Commands: help/? exit/quit", file=out_stream)
    print("REPL command layer (not engine directives):", file=out_stream)
    print("  state", file=out_stream)
    print("  preview <input>", file=out_stream)
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
    print("preview is a deterministic dry-run and never mutates live state.", file=out_stream)
    print("Only question prompts accept yes/no confirmations", file=out_stream)
    print("Other clarify prompts are errors and do not accept yes/no", file=out_stream)


def _render_state_lines(state: State) -> list[str]:
    premise = get_premise_value(state)
    premise_line = "premise: (none)" if premise is None else f"premise: {premise}"

    all_policy_items = get_policy_items(state)
    if not all_policy_items:
        return [premise_line, "policies: (none)"]

    use_items = set(get_policy_items(state, "use"))
    policy_items: list[tuple[str, str]] = []
    for item in all_policy_items:
        value = "use" if item in use_items else "prohibit"
        policy_items.append((item, value))

    lines = [premise_line, "policies:"]
    for item, value in policy_items:
        lines.append(f"- {value} {item}")
    return lines


def _render_decision_lines(decision: Decision) -> list[str]:
    kind = decision["kind"]
    if kind == DECISION_PASSTHROUGH:
        return ["passthrough"]
    if kind == DECISION_CLARIFY:
        prompt = decision["prompt_to_user"] or ""
        prompt_lines = prompt.splitlines() if prompt else [""]
        if prompt.endswith("?"):
            return [f"confirm: {prompt_lines[0]}", *prompt_lines[1:]]
        return [f"error: {prompt_lines[0]}", *prompt_lines[1:]]

    state = decision["state"]
    assert state is not None
    return ["updated", *_render_state_lines(state)]


def _print_decision_lines(decision: Decision, out_stream: TextIO, *, leading_blank: bool) -> None:
    if leading_blank:
        print("", file=out_stream)
    for line in _render_decision_lines(decision):
        print(line, file=out_stream)


def _render_diff_lines(preview_result: PreviewResult) -> list[str]:
    diff = preview_result["diff"]
    lines = [f"would_mutate: {'yes' if preview_would_mutate(preview_result) else 'no'}", "diff:"]

    premise = diff["premise"]
    if premise["changed"]:
        before = "(none)" if premise["before"] is None else premise["before"]
        after = "(none)" if premise["after"] is None else premise["after"]
        lines.append(f"- premise: {before} -> {after}")

    policies = diff["policies"]
    for item, value in sorted(policies["added"].items()):
        lines.append(f"- + {value} {item}")
    for item, value in sorted(policies["removed"].items()):
        lines.append(f"- - {value} {item}")
    for item, change in sorted(policies["changed"].items()):
        lines.append(f"- ~ {change['before']} {item} -> {change['after']} {item}")

    if len(lines) == 2:
        lines.append("- (none)")
    return lines


def _print_preview_lines(
    preview_result: PreviewResult,
    out_stream: TextIO,
    *,
    leading_blank: bool,
    command_name: str,
) -> None:
    if leading_blank:
        print("", file=out_stream)
    print(command_name, file=out_stream)
    for line in _render_decision_lines(get_preview_decision(preview_result)):
        print(line, file=out_stream)
    for line in _render_diff_lines(preview_result):
        print(line, file=out_stream)


def _print_command_error(out_stream: TextIO, *, leading_blank: bool, message: str) -> None:
    if leading_blank:
        print("", file=out_stream)
    print(f"error: {message}", file=out_stream)


def _write_json_line(out_stream: TextIO, payload: dict[str, object]) -> None:
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True), file=out_stream)


def _json_step_payload(result: StepResult, *, command: str) -> dict[str, object]:
    payload: dict[str, object] = dict(result)
    payload["command"] = command
    return payload


def _json_preview_payload(result: PreviewResult, *, command: str) -> dict[str, object]:
    payload: dict[str, object] = dict(result)
    payload["command"] = command
    return payload


def _json_state_payload(state: State) -> dict[str, object]:
    return {
        "output_version": OUTPUT_VERSION,
        "mode": "state",
        "command": "state",
        "state": state,
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
        "--initial-checkpoint-json": "initial_checkpoint_json",
        "--initial-checkpoint-file": "initial_checkpoint_file",
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
    has_checkpoint_json = "initial_checkpoint_json" in options
    has_checkpoint_file = "initial_checkpoint_file" in options

    if has_state_json and has_state_file:
        return {}, "state preload options are mutually exclusive"
    if has_checkpoint_json and has_checkpoint_file:
        return {}, "checkpoint preload options are mutually exclusive"
    if (has_state_json or has_state_file) and (has_checkpoint_json or has_checkpoint_file):
        return {}, "state preload and checkpoint preload are mutually exclusive"

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
        return
    if "initial_checkpoint_json" in options:
        raw = options["initial_checkpoint_json"]
        assert isinstance(raw, str)
        engine.import_checkpoint_json(raw)
        return
    if "initial_checkpoint_file" in options:
        path = options["initial_checkpoint_file"]
        assert isinstance(path, str)
        engine.import_checkpoint_json(_read_utf8_file(path))


def _has_pending_clarification(engine: Engine) -> bool:
    return engine.has_pending_clarification()


def _normalize_confirmation_token(value: str) -> str:
    normalized = value.strip().lower()
    while normalized and normalized[-1] in ".,!?":
        normalized = normalized[:-1]
    return " ".join(normalized.split())


def _is_confirmation_input(value: str) -> bool:
    normalized = _normalize_confirmation_token(value)
    return normalized in _AFFIRMATIVE_CONFIRMATIONS or normalized in _NEGATIVE_CONFIRMATIONS


def run_repl(
    in_stream: TextIO,
    out_stream: TextIO,
    *,
    json_mode: bool = False,
    engine: Engine | None = None,
) -> None:
    active_engine = create_engine() if engine is None else engine

    if _is_interactive(in_stream, out_stream):
        print("Context Compiler REPL (0.5). Type help for commands.", file=out_stream)
        print("Non-directive input is passthrough.", file=out_stream)

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
                for line in _render_state_lines(active_engine.state):
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
                    if _has_pending_clarification(active_engine) and not _is_confirmation_input(
                        payload
                    ):
                        _print_command_error(
                            out_stream,
                            leading_blank=True,
                            message=_STEP_PENDING_CONFIRMATION_ERROR,
                        )
                        continue
                    result: StepResult = controller_step(active_engine, payload)
                    _print_decision_lines(get_step_decision(result), out_stream, leading_blank=True)
                    continue

            preview_command = None
            payload = ""
            if user_input.startswith("preview "):
                preview_command = "preview"
                payload = user_input[len("preview ") :]
            elif token == "preview":
                preview_command = "preview"

            if preview_command == "preview":
                if payload.strip() == "":
                    _print_command_error(
                        out_stream,
                        leading_blank=True,
                        message="preview requires input.\nUse 'preview <input>'.",
                    )
                    continue
                preview_result = controller_preview(active_engine, payload)
                _print_preview_lines(
                    preview_result,
                    out_stream,
                    leading_blank=True,
                    command_name=preview_command,
                )
                continue

            result = controller_step(active_engine, user_input)
            _print_decision_lines(get_step_decision(result), out_stream, leading_blank=True)
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
                _write_json_line(out_stream, _json_state_payload(active_engine.state))
            else:
                for state_line in _render_state_lines(active_engine.state):
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
                if _has_pending_clarification(active_engine) and not _is_confirmation_input(
                    payload
                ):
                    if json_mode:
                        _write_json_line(
                            out_stream,
                            _json_error_payload(
                                command="step",
                                code="pending_confirmation_required",
                                message=_STEP_PENDING_CONFIRMATION_ERROR,
                            ),
                        )
                    else:
                        _print_command_error(
                            out_stream,
                            leading_blank=False,
                            message=_STEP_PENDING_CONFIRMATION_ERROR,
                        )
                    continue
                result = controller_step(active_engine, payload)
                if json_mode:
                    _write_json_line(out_stream, _json_step_payload(result, command="step"))
                else:
                    _print_decision_lines(
                        get_step_decision(result), out_stream, leading_blank=False
                    )
                continue

        preview_command = None
        payload = ""
        if user_input.startswith("preview "):
            preview_command = "preview"
            payload = user_input[len("preview ") :]
        elif token == "preview":
            preview_command = "preview"

        if preview_command == "preview":
            if payload.strip() == "":
                if json_mode:
                    _write_json_line(
                        out_stream,
                        _json_error_payload(
                            command="preview",
                            code="missing_preview_input",
                            message="preview requires input.\nUse 'preview <input>'.",
                        ),
                    )
                else:
                    _print_command_error(
                        out_stream,
                        leading_blank=False,
                        message="preview requires input.\nUse 'preview <input>'.",
                    )
                continue
            preview_result = controller_preview(active_engine, payload)
            if json_mode:
                _write_json_line(
                    out_stream, _json_preview_payload(preview_result, command="preview")
                )
            else:
                _print_preview_lines(
                    preview_result,
                    out_stream,
                    leading_blank=False,
                    command_name=preview_command,
                )
            continue

        result = controller_step(active_engine, user_input)
        if json_mode:
            _write_json_line(out_stream, _json_step_payload(result, command="input"))
        else:
            _print_decision_lines(get_step_decision(result), out_stream, leading_blank=False)


def main() -> int:  # pragma: no cover
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

    engine = create_engine()
    try:
        _apply_preload_from_options(engine, options)
    except (OSError, ValueError) as exc:
        print(f"error: preload failed: {exc}", file=sys.stderr)
        return 1

    run_repl(sys.stdin, sys.stdout, json_mode=json_mode, engine=engine)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
