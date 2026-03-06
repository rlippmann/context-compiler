import json
from io import StringIO

from hypothesis import assume, given
from hypothesis import strategies as st

from context_compiler import create_engine
from context_compiler.repl import run_repl

LINE_TEXT = st.text(
    alphabet=st.characters(blacklist_characters="\n\r"),
    max_size=80,
)


def _run_repl_lines(lines: list[str]) -> tuple[str, list[dict[str, object]]]:
    in_stream = StringIO("".join(f"{line}\n" for line in lines))
    out_stream = StringIO()
    run_repl(in_stream, out_stream)
    raw = out_stream.getvalue()
    parsed = [json.loads(line) for line in raw.splitlines() if line.strip()]
    return raw, parsed


@given(st.lists(LINE_TEXT, min_size=0, max_size=40))
def test_repl_matches_engine_for_non_exit_sequences(lines: list[str]) -> None:
    assume(all(line.strip().lower() not in {"exit", "quit"} for line in lines))

    _, repl_decisions = _run_repl_lines(lines)

    engine = create_engine()
    oracle = [engine.step(line) for line in lines]
    assert repl_decisions == oracle


@given(st.lists(LINE_TEXT, min_size=0, max_size=40))
def test_repl_is_deterministic_for_same_input(lines: list[str]) -> None:
    raw1, parsed1 = _run_repl_lines(lines)
    raw2, parsed2 = _run_repl_lines(lines)

    assert raw1 == raw2
    assert parsed1 == parsed2


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
    _, repl_decisions = _run_repl_lines(lines)

    engine = create_engine()
    oracle = [engine.step(line) for line in prefix]
    assert repl_decisions == oracle


@given(st.lists(LINE_TEXT, min_size=0, max_size=40))
def test_repl_emits_canonical_json_per_output_line(lines: list[str]) -> None:
    assume(all(line.strip().lower() not in {"exit", "quit"} for line in lines))
    raw, _ = _run_repl_lines(lines)

    for output_line in raw.splitlines():
        if not output_line.strip():
            continue
        parsed = json.loads(output_line)
        canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
        assert output_line == canonical
