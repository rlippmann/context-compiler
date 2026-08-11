"""Example 2: explicit premise lifecycle with deterministic replacement."""

from _util import print_decision_summary, print_engine_observations

from context_compiler import Engine


def main() -> None:
    engine = Engine()

    print("User: set premise vegetarian curry")
    decision1 = engine.step("set premise vegetarian curry")
    print_decision_summary(decision1)
    print_engine_observations(premise=engine.premise, policies=engine.policies)
    print()

    print("User: change premise to vegan curry")
    decision2 = engine.step("change premise to vegan curry")
    print_decision_summary(decision2)
    print_engine_observations(
        premise=engine.premise,
        policies=engine.policies,
        label="state after explicit premise change",
    )


if __name__ == "__main__":
    main()
