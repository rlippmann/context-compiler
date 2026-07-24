"""Example 6: explicit step sequencing and state restore."""

from _util import print_decision_summary, print_state_summary

from context_compiler import create_engine


def main() -> None:
    engine = create_engine()
    turns = [
        "prohibit peanuts",
        "set premise vegetarian curry",
        "change premise to vegan curry",
    ]

    print("Sequence directives through engine.step():")
    for turn in turns:
        print(f"User: {turn}")
        print_decision_summary(engine.step(turn))
    print()

    state_json = engine.export_json()
    restored = create_engine()
    restored.import_json(state_json)

    print("JSON restore keeps authority state:")
    print_state_summary(restored.state, "restored state")


if __name__ == "__main__":
    main()
