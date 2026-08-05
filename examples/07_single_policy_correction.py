"""Example 7: explicit single-policy correction without reset policies."""

from _util import print_decision_summary, print_engine_observations

from context_compiler import create_engine


def main() -> None:
    engine = create_engine()

    print("User: prohibit peanuts")
    decision1 = engine.step("prohibit peanuts")
    print_decision_summary(decision1)
    print()

    print("User: remove policy peanuts")
    decision2 = engine.step("remove policy peanuts")
    print_decision_summary(decision2)
    print()

    print("User: use peanuts")
    decision3 = engine.step("use peanuts")
    print_decision_summary(decision3)
    print()

    print_engine_observations(
        premise=engine.premise,
        policies=engine.policies,
        label="final state",
    )


if __name__ == "__main__":
    main()
