import sys
from typing import TextIO

from experimental.preprocessor.output_validation import parse_preprocessor_output

from . import __version__, create_engine, get_policy_items, get_premise_value
from .controller import PreviewResult, StepResult
from .controller import preview as controller_preview
from .controller import step as controller_step
from .decision_constants import DECISION_CLARIFY, DECISION_PASSTHROUGH
from .engine import Decision, DecisionKind, Engine, State

_EXIT_TOKENS = {"exit", "quit"}
_HELP_TOKENS = {"help", "?"}
_MULTI_COMMAND_PROMPT = "Multiple commands detected.\nEnter one command per line."
_AFFIRMATIVE_CONFIRMATIONS = {"yes", "yes please", "yep", "yeah", "sure", "ok", "okay"}
_NEGATIVE_CONFIRMATIONS = {"no", "nope", "no thanks"}
_STEP_PENDING_CONFIRMATION_ERROR = (
    "step command only accepts confirmation while clarification is pending.\n"
    "Use yes/no (or variants), or use preview/explain/state."
)
_CLI_HELP_TEXT = """Usage:
  context-compiler [--help] [--version] [--with-preprocessor]

Options:
  --help                Show this help message and exit.
  --version             Show the installed context-compiler version and exit.
  --with-preprocessor   Enable preprocessor before each REPL turn (heuristic + validation only)
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
    lines = [f"would_mutate: {'yes' if preview_result['would_mutate'] else 'no'}", "diff:"]

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
    for line in _render_decision_lines(preview_result["decision"]):
        print(line, file=out_stream)
    for line in _render_diff_lines(preview_result):
        print(line, file=out_stream)


def _print_command_error(out_stream: TextIO, *, leading_blank: bool, message: str) -> None:
    if leading_blank:
        print("", file=out_stream)
    print(f"error: {message}", file=out_stream)


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


def _compile_input(raw_input: str, engine: Engine, *, use_preprocessor: bool) -> str:
    if not use_preprocessor:
        return raw_input
    if _has_pending_clarification(engine):
        return raw_input
    parsed = parse_preprocessor_output(raw_input, source_input=raw_input)
    return parsed if parsed is not None else raw_input


def run_repl(in_stream: TextIO, out_stream: TextIO, *, use_preprocessor: bool = False) -> None:
    engine = create_engine()

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
                for line in _render_state_lines(engine.state):
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
                    if _has_pending_clarification(engine) and not _is_confirmation_input(payload):
                        _print_command_error(
                            out_stream,
                            leading_blank=True,
                            message=_STEP_PENDING_CONFIRMATION_ERROR,
                        )
                        continue
                    compile_input = _compile_input(
                        payload, engine, use_preprocessor=use_preprocessor
                    )
                    result: StepResult = controller_step(engine, compile_input)
                    _print_decision_lines(result["decision"], out_stream, leading_blank=True)
                    continue

            preview_command: str | None = None
            payload = ""
            if user_input.startswith("preview "):
                preview_command = "preview"
                payload = user_input[len("preview ") :]
            elif token == "preview":
                preview_command = "preview"
            elif user_input.startswith("explain "):
                preview_command = "explain"
                payload = user_input[len("explain ") :]
            elif token == "explain":
                preview_command = "explain"

            if preview_command is not None:
                if payload.strip() == "":
                    message = f"{preview_command} requires input.\nUse '{preview_command} <input>'."
                    _print_command_error(
                        out_stream,
                        leading_blank=True,
                        message=message,
                    )
                    continue
                compile_input = _compile_input(payload, engine, use_preprocessor=use_preprocessor)
                preview_result = controller_preview(engine, compile_input)
                _print_preview_lines(
                    preview_result,
                    out_stream,
                    leading_blank=True,
                    command_name=preview_command,
                )
                continue

            compile_input = _compile_input(user_input, engine, use_preprocessor=use_preprocessor)
            result = controller_step(engine, compile_input)
            _print_decision_lines(result["decision"], out_stream, leading_blank=True)
        return

    for line in in_stream:
        if _has_embedded_newline(line):
            _print_decision_lines(_multi_command_decision(), out_stream, leading_blank=False)
            continue
        user_input = line.rstrip("\n")
        if user_input.strip().lower() in _EXIT_TOKENS:
            return

        token = user_input.strip().lower()
        if token == "state":
            for state_line in _render_state_lines(engine.state):
                print(state_line, file=out_stream)
            continue

        if user_input.startswith("step"):
            payload = user_input[4:].lstrip() if user_input != "step" else ""
            if token == "step" and payload == "":
                _print_command_error(
                    out_stream,
                    leading_blank=False,
                    message="step requires input.\nUse 'step <input>'.",
                )
                continue
            if payload != "" and (user_input == "step" or user_input.startswith("step ")):
                if _has_pending_clarification(engine) and not _is_confirmation_input(payload):
                    _print_command_error(
                        out_stream,
                        leading_blank=False,
                        message=_STEP_PENDING_CONFIRMATION_ERROR,
                    )
                    continue
                compile_input = _compile_input(payload, engine, use_preprocessor=use_preprocessor)
                result = controller_step(engine, compile_input)
                _print_decision_lines(result["decision"], out_stream, leading_blank=False)
                continue

        preview_command = None
        payload = ""
        if user_input.startswith("preview "):
            preview_command = "preview"
            payload = user_input[len("preview ") :]
        elif token == "preview":
            preview_command = "preview"
        elif user_input.startswith("explain "):
            preview_command = "explain"
            payload = user_input[len("explain ") :]
        elif token == "explain":
            preview_command = "explain"

        if preview_command is not None:
            if payload.strip() == "":
                message = f"{preview_command} requires input.\nUse '{preview_command} <input>'."
                _print_command_error(
                    out_stream,
                    leading_blank=False,
                    message=message,
                )
                continue
            compile_input = _compile_input(payload, engine, use_preprocessor=use_preprocessor)
            preview_result = controller_preview(engine, compile_input)
            _print_preview_lines(
                preview_result,
                out_stream,
                leading_blank=False,
                command_name=preview_command,
            )
            continue

        compile_input = _compile_input(user_input, engine, use_preprocessor=use_preprocessor)
        result = controller_step(engine, compile_input)
        _print_decision_lines(result["decision"], out_stream, leading_blank=False)


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

    if args == ["--with-preprocessor"]:
        run_repl(sys.stdin, sys.stdout, use_preprocessor=True)
        return 0

    bad_arg = args[0]
    print(f"error: unknown option '{bad_arg}'", file=sys.stderr)
    print("Try 'context-compiler --help' for usage.", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
