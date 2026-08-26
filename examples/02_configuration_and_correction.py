"""Example 2: explicit contextual-premise lifecycle with deterministic replacement."""

from _util import print_decision_summary, print_engine_observations

from context_compiler import Engine


def main() -> None:
    engine = Engine()

    print("User: set premise project deadline is Friday")
    decision1 = engine.step("set premise project deadline is Friday")
    print_decision_summary(decision1)
    print_engine_observations(premise=engine.premise, policies=engine.policies)
    print()

    print("User: change premise to project deadline is Thursday")
    decision2 = engine.step("change premise to project deadline is Thursday")
    print_decision_summary(decision2)
    print_engine_observations(
        premise=engine.premise,
        policies=engine.policies,
        label="state after explicit premise change",
    )


if __name__ == "__main__":
    main()
