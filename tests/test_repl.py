import json
from io import StringIO

from context_compiler.repl import run_repl


class _TTYStringIO(StringIO):
    def isatty(self) -> bool:
        return True


def _run_interactive_lines(text: str) -> list[str]:
    out = _TTYStringIO()
    run_repl(_TTYStringIO(text), out)
    return [line for line in out.getvalue().splitlines() if line.strip()]


def _run_session(text: str) -> list[dict[str, object]]:
    out = StringIO()
    run_repl(StringIO(text), out)
    lines = [line for line in out.getvalue().splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def test_repl_update_flow() -> None:
    decisions = _run_session("set premise concise\nquit\n")

    assert decisions == [
        {
            "kind": "update",
            "prompt_to_user": None,
            "state": {"premise": "concise", "policies": {}, "version": 2},
        }
    ]


def test_repl_clarify_flow() -> None:
    decisions = _run_session("don't use docker\nuse kubectl instead of docker\nquit\n")
    expected_prompt = (
        '"docker" is currently prohibited. Did you mean to remove it and use "kubectl" instead?'
    )

    assert decisions == [
        {
            "kind": "update",
            "prompt_to_user": None,
            "state": {"premise": None, "policies": {"docker": "prohibit"}, "version": 2},
        },
        {
            "kind": "clarify",
            "prompt_to_user": expected_prompt,
            "state": None,
        },
    ]


def test_repl_exit_and_quit_terminate_session() -> None:
    decisions_exit = _run_session("exit\nset premise concise\n")
    decisions_quit = _run_session("quit\nset premise concise\n")

    assert decisions_exit == []
    assert decisions_quit == []


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
        "  don't use <item>",
        "  use <new item> instead of <old item>",
        "  clear premise",
        "  reset policies",
        "  clear state",
        "Only question prompts accept yes/no confirmations",
        "Other clarify prompts are errors and do not accept yes/no",
        'State schema: {"premise": ..., "policies": ..., "version": 2}',
    ]
    assert lines[0] == "Context Compiler REPL (0.5). Type help for commands."
    assert lines[1] == "Non-directive input is passthrough."
    assert lines[2:15] == expected_help
    assert lines[15:28] == expected_help


def test_repl_non_interactive_keeps_json_output() -> None:
    out = StringIO()
    run_repl(StringIO("hello\nquit\n"), out)

    lines = out.getvalue().splitlines()
    expected = '{"kind":"passthrough","prompt_to_user":null,"state":null}'
    assert lines == [expected]


def test_repl_invalid_directive_near_misses_remain_passthrough() -> None:
    decisions = _run_session("actually use uv\nno use peanuts\nallow docker\nquit\n")

    assert decisions == [
        {"kind": "passthrough", "prompt_to_user": None, "state": None},
        {"kind": "passthrough", "prompt_to_user": None, "state": None},
        {"kind": "passthrough", "prompt_to_user": None, "state": None},
    ]


def test_repl_contradiction_clarify_is_not_pending_confirmable() -> None:
    decisions = _run_session("use docker\ndon't use docker\nno\nquit\n")

    assert decisions == [
        {
            "kind": "update",
            "prompt_to_user": None,
            "state": {"premise": None, "policies": {"docker": "use"}, "version": 2},
        },
        {
            "kind": "clarify",
            "prompt_to_user": "Cannot set prohibit for 'docker' while it is use.",
            "state": None,
        },
        {
            "kind": "passthrough",
            "prompt_to_user": None,
            "state": None,
        },
    ]


def test_repl_replacement_clarify_requires_confirmation_tokens_and_persists_until_resolved() -> (
    None
):
    decisions = _run_session("use podman instead of docker\nmaybe\nyes please!!\nquit\n")

    expected_prompt = 'Did you mean to use "podman" instead?'
    assert decisions == [
        {
            "kind": "clarify",
            "prompt_to_user": expected_prompt,
            "state": None,
        },
        {
            "kind": "clarify",
            "prompt_to_user": expected_prompt,
            "state": None,
        },
        {
            "kind": "update",
            "prompt_to_user": None,
            "state": {"premise": None, "policies": {"podman": "use"}, "version": 2},
        },
    ]


def test_repl_interactive_prints_confirm_and_error_for_clarify_types() -> None:
    error_out = _TTYStringIO()
    run_repl(_TTYStringIO("use docker\ndon't use docker\nquit\n"), error_out)
    error_lines = error_out.getvalue().splitlines()
    assert "error: Cannot set prohibit for 'docker' while it is use." in error_lines

    confirm_out = _TTYStringIO()
    run_repl(_TTYStringIO("use podman instead of docker\nquit\n"), confirm_out)
    confirm_lines = confirm_out.getvalue().splitlines()
    assert 'confirm: Did you mean to use "podman" instead?' in confirm_lines


def test_repl_replacement_negative_confirmation_returns_update_unchanged_and_clears_pending() -> (
    None
):
    decisions = _run_session(
        "use docker\ndon't use podman\nuse podman instead of docker\nno\nno\nquit\n"
    )

    prompt = (
        '"podman" is currently prohibited. Did you mean to remove "docker" and use '
        '"podman" instead?'
    )
    unchanged = {"premise": None, "policies": {"docker": "use", "podman": "prohibit"}, "version": 2}
    assert decisions == [
        {
            "kind": "update",
            "prompt_to_user": None,
            "state": {"premise": None, "policies": {"docker": "use"}, "version": 2},
        },
        {
            "kind": "update",
            "prompt_to_user": None,
            "state": unchanged,
        },
        {
            "kind": "clarify",
            "prompt_to_user": prompt,
            "state": None,
        },
        {
            "kind": "update",
            "prompt_to_user": None,
            "state": unchanged,
        },
        {
            "kind": "passthrough",
            "prompt_to_user": None,
            "state": None,
        },
    ]


def test_repl_premise_lifecycle_outputs_expected_state_shape() -> None:
    decisions = _run_session(
        "set premise Use concise answers\n"
        "set premise Use verbose answers\n"
        "change premise to Use verbose answers\n"
        "quit\n"
    )

    assert decisions == [
        {
            "kind": "update",
            "prompt_to_user": None,
            "state": {
                "premise": "Use concise answers",
                "policies": {},
                "version": 2,
            },
        },
        {
            "kind": "clarify",
            "prompt_to_user": "Premise already exists. Use 'change premise to ...' to replace it.",
            "state": None,
        },
        {
            "kind": "update",
            "prompt_to_user": None,
            "state": {
                "premise": "Use verbose answers",
                "policies": {},
                "version": 2,
            },
        },
    ]


def test_repl_interactive_renders_updated_state_blocks_for_multiple_operations() -> None:
    lines = _run_interactive_lines("set premise concise replies\nuse docker\nclear premise\nquit\n")
    state_lines = [line for line in lines if line.startswith("{") and '"version": 2' in line]

    assert "updated" in lines
    assert "state:" in lines
    assert len(state_lines) == 3
    for state_line in state_lines:
        parsed = json.loads(state_line)
        assert set(parsed.keys()) == {"premise", "policies", "version"}
        canonical = json.dumps(parsed, sort_keys=True)
        assert state_line == canonical


def test_repl_interactive_confirmation_token_variants_resolve_pending_clarify() -> None:
    lines_yes = _run_interactive_lines("use podman instead of docker\nyeah\nquit\n")
    state_yes = [line for line in lines_yes if line.startswith("{") and '"version": 2' in line]
    assert 'confirm: Did you mean to use "podman" instead?' in lines_yes
    assert state_yes[-1] == '{"policies": {"podman": "use"}, "premise": null, "version": 2}'

    lines_ok = _run_interactive_lines("use buildah instead of docker\nok\nquit\n")
    state_ok = [line for line in lines_ok if line.startswith("{") and '"version": 2' in line]
    assert 'confirm: Did you mean to use "buildah" instead?' in lines_ok
    assert state_ok[-1] == '{"policies": {"buildah": "use"}, "premise": null, "version": 2}'

    lines_nope = _run_interactive_lines("use nerdctl instead of docker\nnope\nquit\n")
    state_nope = [line for line in lines_nope if line.startswith("{") and '"version": 2' in line]
    assert 'confirm: Did you mean to use "nerdctl" instead?' in lines_nope
    assert state_nope[-1] == '{"policies": {}, "premise": null, "version": 2}'

    lines_no_thanks = _run_interactive_lines("use helm instead of docker\nno thanks\nquit\n")
    state_no_thanks = [
        line for line in lines_no_thanks if line.startswith("{") and '"version": 2' in line
    ]
    assert 'confirm: Did you mean to use "helm" instead?' in lines_no_thanks
    assert state_no_thanks[-1] == '{"policies": {}, "premise": null, "version": 2}'


def test_repl_interactive_admin_idempotency_outputs_updated_with_unchanged_state() -> None:
    lines = _run_interactive_lines("clear premise\nclear state\nreset policies\nquit\n")
    state_lines = [line for line in lines if line.startswith("{") and '"version": 2' in line]
    expected_state = '{"policies": {}, "premise": null, "version": 2}'

    assert lines.count("updated") == 3
    assert lines.count("state:") == 3
    assert state_lines == [expected_state, expected_state, expected_state]


def test_repl_interactive_confirm_vs_error_alignment_for_actual_clarify_behaviors() -> None:
    lines = _run_interactive_lines(
        "set premise concise\n"
        "set premise verbose\n"
        "use docker\n"
        "don't use docker\n"
        "use podman instead of buildx\n"
        "quit\n"
    )

    assert "error: Premise already exists. Use 'change premise to ...' to replace it." in lines
    assert "error: Cannot set prohibit for 'docker' while it is use." in lines
    assert 'confirm: Did you mean to use "podman" instead?' in lines


def test_repl_interactive_passthrough_prints_passthrough_label() -> None:
    lines = _run_interactive_lines("actually use uv\nquit\n")
    assert "passthrough" in lines


def test_repl_interactive_blank_line_is_ignored_without_output() -> None:
    lines = _run_interactive_lines("\nset premise concise\nquit\n")
    state_lines = [line for line in lines if line.startswith("{") and '"version": 2' in line]

    assert lines[0] == "Context Compiler REPL (0.5). Type help for commands."
    assert lines[1] == "Non-directive input is passthrough."
    assert lines.count("updated") == 1
    assert lines.count("state:") == 1
    assert state_lines == ['{"policies": {}, "premise": "concise", "version": 2}']


def test_repl_interactive_eof_returns_cleanly_after_startup_banner() -> None:
    lines = _run_interactive_lines("")
    assert lines == [
        "Context Compiler REPL (0.5). Type help for commands.",
        "Non-directive input is passthrough.",
    ]
