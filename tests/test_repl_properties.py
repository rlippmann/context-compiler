from io import StringIO

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from context_compiler import create_engine
from context_compiler.repl import run_repl

pytestmark = pytest.mark.contract

LINE_TEXT = st.text(
    alphabet=st.characters(blacklist_characters="\n\r"),
    max_size=80,
)


def _run_repl_lines(lines: list[str]) -> tuple[str, list[str]]:
    in_stream = StringIO("".join(f"{line}\n" for line in lines))
    out_stream = StringIO()
    run_repl(in_stream, out_stream)
    raw = out_stream.getvalue()
    rendered = [line for line in raw.splitlines() if line.strip()]
    return raw, rendered


def _oracle_render_decision(decision: dict[str, object]) -> list[str]:
    kind = decision["kind"]
    if kind == "passthrough":
        return ["passthrough"]

    if kind == "clarify":
        prompt_obj = decision["prompt_to_user"]
        prompt = prompt_obj if isinstance(prompt_obj, str) else ""
        prompt_lines = prompt.splitlines() if prompt else [""]
        if prompt.endswith("?"):
            return [f"confirm: {prompt_lines[0]}", *prompt_lines[1:]]
        return [f"error: {prompt_lines[0]}", *prompt_lines[1:]]

    state_obj = decision["state"]
    assert isinstance(state_obj, dict)
    premise = state_obj.get("premise")
    premise_line = "premise: (none)" if premise is None else f"premise: {premise}"

    policies_obj = state_obj.get("policies")
    assert isinstance(policies_obj, dict)
    policy_items = sorted(policies_obj.items())
    if not policy_items:
        return ["updated", premise_line, "policies: (none)"]

    lines = ["updated", premise_line, "policies:"]
    for item, value in policy_items:
        lines.append(f"- {value} {item}")
    return lines


@given(st.lists(LINE_TEXT, min_size=0, max_size=40))
def test_repl_matches_engine_for_non_exit_sequences(lines: list[str]) -> None:
    assume(all(line.strip().lower() not in {"exit", "quit"} for line in lines))

    _, repl_lines = _run_repl_lines(lines)

    engine = create_engine()
    oracle_lines = [
        rendered_line
        for line in lines
        for rendered_line in _oracle_render_decision(engine.step(line))
    ]
    assert repl_lines == oracle_lines


@given(st.lists(LINE_TEXT, min_size=0, max_size=40))
def test_repl_is_deterministic_for_same_input(lines: list[str]) -> None:
    raw1, rendered1 = _run_repl_lines(lines)
    raw2, rendered2 = _run_repl_lines(lines)

    assert raw1 == raw2
    assert rendered1 == rendered2


@given(
    st.lists(LINE_TEXT, min_size=0, max_size=20),
    st.sampled_from(["exit", "quit", " EXIT ", "QuIt"]),
    st.lists(LINE_TEXT, min_size=0, max_size=20),
)
def test_repl_stops_processing_after_exit_or_quit(
    prefix: list[str], stop_token: str, suffix: list[str]
) -> None:
    assume(all(line.strip().lower() not in {"exit", "quit"} for line in prefix))
    lines = [*prefix, stop_token, *suffix]
    _, repl_lines = _run_repl_lines(lines)

    engine = create_engine()
    oracle_lines = [
        rendered_line
        for line in prefix
        for rendered_line in _oracle_render_decision(engine.step(line))
    ]
    assert repl_lines == oracle_lines


@given(st.lists(LINE_TEXT, min_size=0, max_size=40))
def test_repl_emits_human_readable_output_lines(lines: list[str]) -> None:
    assume(all(line.strip().lower() not in {"exit", "quit"} for line in lines))
    raw, _ = _run_repl_lines(lines)

    for output_line in raw.splitlines():
        if not output_line.strip():
            continue
        assert not output_line.startswith("{")
        assert '"kind"' not in output_line
        assert '"prompt_to_user"' not in output_line
        assert '"state"' not in output_line
