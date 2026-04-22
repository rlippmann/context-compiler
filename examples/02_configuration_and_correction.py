"""Example 2: explicit premise lifecycle with deterministic replacement."""

from context_compiler import create_engine
from examples._util import print_decision_summary, print_state_summary


def main() -> None:
    engine = create_engine()

    print("User: set premise vegetarian curry")
    decision1 = engine.step("set premise vegetarian curry")
    print_decision_summary(decision1)
    print_state_summary(engine.state)
    print()

    print("User: change premise to vegan curry")
    decision2 = engine.step("change premise to vegan curry")
    print_decision_summary(decision2)
    print_state_summary(engine.state, "state after explicit premise change")


if __name__ == "__main__":
    main()
