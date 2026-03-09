"""Example 2: conversational configuration with correction (last-write-wins)."""

from _util import print_json

from context_compiler import create_engine


def main() -> None:
    engine = create_engine()

    print("User: I'm using MacBook M3")
    decision1 = engine.step("I'm using MacBook M3")
    print("Decision:")
    print_json(decision1)
    print("State:")
    print_json(engine.state)
    print()

    print("User: actually MacBook M2")
    decision2 = engine.step("actually MacBook M2")
    print("Decision:")
    print_json(decision2)
    print("State (last write wins):")
    print_json(engine.state)


if __name__ == "__main__":
    main()
