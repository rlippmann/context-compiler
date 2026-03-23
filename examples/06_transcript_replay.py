"""Example 6: transcript replay with compile_transcript and apply_transcript."""

from _util import print_json

from context_compiler import compile_transcript, create_engine


def main() -> None:
    transcript: list[dict[str, object]] = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "don't use peanuts"},
        {"role": "assistant", "content": "Understood"},
        {"role": "user", "content": "set premise vegetarian curry"},
        {"role": "user", "content": "change premise to vegan curry"},
    ]

    print("Replay from fresh engine (compile_transcript):")
    print_json(compile_transcript(transcript))
    print()

    engine = create_engine()
    engine.step("don't use shellfish")
    print("Replay onto current engine (engine.apply_transcript):")
    print_json(engine.apply_transcript(transcript))


if __name__ == "__main__":
    main()
