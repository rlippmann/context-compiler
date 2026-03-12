"""Demo 6: host-side prompt replacement from authoritative compiled state."""

from context_compiler import create_engine
from context_compiler.const import FOCUS_PRIMARY, STATE_FACTS
from demos.common import is_verbose, print_info_report

DEMO_NAME = "06_context_compaction — superseded directives eliminated"
FINAL_FOCUS = "chickpea curry"
SCALING_TURNS = (5, 20, 50)


def _build_baseline_prompt(transcript_turns: list[str]) -> str:
    transcript_lines = "\n".join(f"User: {turn}" for turn in transcript_turns)
    return (
        "You are a helpful assistant.\n"
        "Use the full transcript context below:\n"
        f"{transcript_lines}\n"
        "Respond using the latest user preference."
    )


def _build_compiled_prompt(compiled_focus: str) -> str:
    return (
        "You are a helpful assistant.\n"
        "Host-side authoritative compiled context:\n"
        f"- facts.focus.primary: {compiled_focus}\n"
        "Use only this compiled state as the active context."
    )


def _build_turns(turn_count: int) -> list[str]:
    if turn_count < 2:
        raise ValueError("turn_count must be at least 2")
    variants = ["vegan", "tofu", "lentil", "vegetarian"]
    turns = ["use vegetarian curry"]
    for index in range(turn_count - 2):
        variant = variants[index % len(variants)]
        turns.append(f"actually {variant} curry")
    turns.append(f"actually {FINAL_FOCUS}")
    return turns


def _compile_focus(turns: list[str]) -> str:
    engine = create_engine()
    for turn in turns:
        engine.step(turn)
    compiled_focus = engine.state[STATE_FACTS][FOCUS_PRIMARY]
    assert compiled_focus is not None
    return compiled_focus


def _context_metrics(turns: list[str], compiled_context: str) -> tuple[int, int, int]:
    baseline_context = "\n".join(f"User: {turn}" for turn in turns)
    baseline_context_length = len(baseline_context)
    compiled_context_length = len(compiled_context)
    reduction = round((1 - (compiled_context_length / baseline_context_length)) * 100)
    return baseline_context_length, compiled_context_length, reduction


def _print_verbose_report(
    *,
    transcript_turns: list[str],
    compiled_context: str,
    baseline_prompt: str,
    compiled_prompt: str,
    baseline_context_length: int,
    compiled_context_length: int,
    context_reduction: int,
    baseline_prompt_length: int,
    compiled_prompt_length: int,
    prompt_reduction: int,
    scaling_rows: list[tuple[int, int, int, int]],
) -> None:
    print(DEMO_NAME)
    print()
    print("Raw transcript context:")
    for turn in transcript_turns:
        print(f"User: {turn}")
    print()
    print("Compiled context:")
    print(compiled_context)
    print()
    print("Baseline prompt:")
    print(baseline_prompt)
    print()
    print("Compiled prompt:")
    print(compiled_prompt)
    print()
    print("Context scaling:")
    print()
    for turns, baseline_length, compiled_length, reduction in scaling_rows:
        print(f"Turns: {turns}")
        print(f"context: {baseline_length} → {compiled_length} chars")
        print(f"reduction: {reduction}%")
        print()
    print("result: transcript grows linearly; compiled context stays constant")


def _print_compact_report(
    *,
    scaling_rows: list[tuple[int, int, int, int]],
) -> None:
    row_by_turns = {
        turns: (baseline, compiled, reduction)
        for turns, baseline, compiled, reduction in scaling_rows
    }
    five_baseline, five_compiled, five_reduction = row_by_turns[5]
    fifty_baseline, fifty_compiled, fifty_reduction = row_by_turns[50]
    print(DEMO_NAME)
    print(
        f"context scaling: 5 turns {five_baseline} → {five_compiled} chars "
        f"({five_reduction}% reduction); 50 turns {fifty_baseline} → {fifty_compiled} chars "
        f"({fifty_reduction}% reduction)"
    )
    print("result: transcript grows linearly; compiled context stays constant")


def main() -> None:
    transcript_turns = _build_turns(5)
    compiled_focus = _compile_focus(transcript_turns)
    assert compiled_focus == FINAL_FOCUS
    baseline_context = "\n".join(f"User: {turn}" for turn in transcript_turns)
    compiled_context = f"- facts.focus.primary: {compiled_focus}"
    baseline_prompt = _build_baseline_prompt(transcript_turns)
    compiled_prompt = _build_compiled_prompt(compiled_focus)
    baseline_context_length = len(baseline_context)
    compiled_context_length = len(compiled_context)
    context_reduction = round((1 - (compiled_context_length / baseline_context_length)) * 100)
    baseline_prompt_length = len(baseline_prompt)
    compiled_prompt_length = len(compiled_prompt)
    prompt_reduction = round((1 - (compiled_prompt_length / baseline_prompt_length)) * 100)
    scaling_rows: list[tuple[int, int, int, int]] = []
    for turns in SCALING_TURNS:
        scaling_turns = _build_turns(turns)
        scaling_focus = _compile_focus(scaling_turns)
        assert scaling_focus == FINAL_FOCUS
        row_baseline_length, row_compiled_length, row_reduction = _context_metrics(
            scaling_turns, compiled_context
        )
        scaling_rows.append((turns, row_baseline_length, row_compiled_length, row_reduction))

    if is_verbose():
        _print_verbose_report(
            transcript_turns=transcript_turns,
            compiled_context=compiled_context,
            baseline_prompt=baseline_prompt,
            compiled_prompt=compiled_prompt,
            baseline_context_length=baseline_context_length,
            compiled_context_length=compiled_context_length,
            context_reduction=context_reduction,
            baseline_prompt_length=baseline_prompt_length,
            compiled_prompt_length=compiled_prompt_length,
            prompt_reduction=prompt_reduction,
            scaling_rows=scaling_rows,
        )
    else:
        _print_compact_report(scaling_rows=scaling_rows)

    print_info_report(
        name=DEMO_NAME,
        baseline_context_length=baseline_context_length,
        compiled_context_length=compiled_context_length,
        context_reduction_percent=context_reduction,
        baseline_prompt_length=baseline_prompt_length,
        compiled_prompt_length=compiled_prompt_length,
        prompt_reduction_percent=prompt_reduction,
    )


if __name__ == "__main__":
    main()
