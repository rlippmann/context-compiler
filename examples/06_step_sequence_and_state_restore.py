"""Example 6: explicit step sequencing and state restore."""

from _util import print_decision_summary, print_engine_observations

from context_compiler import Engine


def main() -> None:
    engine = Engine()
    turns = [
        "prohibit peanuts",
        "set premise project deadline is Friday",
        "change premise to project deadline is Thursday",
    ]

    print("Sequence directives through engine.step():")
    for turn in turns:
        print(f"User: {turn}")
        decision = engine.step(turn)
        print_decision_summary(decision)
    print()

    # Hosts can persist authoritative state directly instead of replaying prior turns.
    state_json = engine.export_json()
    restored = Engine()
    restored.import_json(state_json)

    print("JSON restore keeps authority state:")
    print_engine_observations(
        premise=restored.premise,
        policies=restored.policies,
        label="restored state",
    )


if __name__ == "__main__":
    main()
