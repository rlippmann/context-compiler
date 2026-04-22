"""Example 6: transcript replay with compile_transcript and apply_transcript."""

from context_compiler import Transcript, compile_transcript, create_engine
from examples._util import print_replay_result_summary


def main() -> None:
    transcript: Transcript = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "prohibit peanuts"},
        {"role": "assistant", "content": "Understood"},
        {"role": "user", "content": "set premise vegetarian curry"},
        {"role": "user", "content": "change premise to vegan curry"},
    ]

    print("Replay from fresh engine (compile_transcript):")
    print_replay_result_summary(compile_transcript(transcript))
    print()

    engine = create_engine()
    engine.step("prohibit shellfish")
    print("Replay onto current engine (engine.apply_transcript):")
    print_replay_result_summary(engine.apply_transcript(transcript))


if __name__ == "__main__":
    main()
