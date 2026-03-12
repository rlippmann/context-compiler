"""Demo 6: host-side prompt replacement from authoritative compiled state."""

from context_compiler import create_engine
from context_compiler.const import FOCUS_PRIMARY, STATE_FACTS
from demos.common import is_verbose, print_info_report

DEMO_NAME = "06_context_compaction — superseded directives eliminated"


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
    print("Context size comparison:")
    print(f"baseline context length: {baseline_context_length}")
    print(f"compiled context length: {compiled_context_length}")
    print(f"reduction: {context_reduction}%")
    print()
    print("Prompt size comparison:")
    print(f"baseline prompt length: {baseline_prompt_length}")
    print(f"compiled prompt length: {compiled_prompt_length}")
    print(f"reduction: {prompt_reduction}%")
    print("result: compiled authoritative state replaced superseded transcript directives")


def _print_compact_report(
    *,
    baseline_context_length: int,
    compiled_context_length: int,
    baseline_prompt_length: int,
    compiled_prompt_length: int,
    context_reduction: int,
    prompt_reduction: int,
) -> None:
    print(DEMO_NAME)
    print(f"context: {baseline_context_length} → {compiled_context_length} chars")
    print(f"prompt: {baseline_prompt_length} → {compiled_prompt_length} chars")
    print(f"reduction: context {context_reduction}%; prompt {prompt_reduction}%")
    print("result: compiled authoritative state replaced superseded transcript directives")


def main() -> None:
    engine = create_engine()
    transcript_turns = [
        "use vegetarian curry",
        "actually vegan curry",
        "actually tofu curry",
        "actually lentil curry",
        "actually chickpea curry",
    ]
    for turn in transcript_turns:
        engine.step(turn)

    compiled_focus = engine.state[STATE_FACTS][FOCUS_PRIMARY]
    assert compiled_focus is not None

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
        )
    else:
        _print_compact_report(
            baseline_context_length=baseline_context_length,
            compiled_context_length=compiled_context_length,
            baseline_prompt_length=baseline_prompt_length,
            compiled_prompt_length=compiled_prompt_length,
            context_reduction=context_reduction,
            prompt_reduction=prompt_reduction,
        )

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
