"""Example 2: explicit premise lifecycle with deterministic replacement."""

from _util import print_json

from context_compiler import create_engine


def main() -> None:
    engine = create_engine()

    print("User: set premise vegetarian curry")
    decision1 = engine.step("set premise vegetarian curry")
    print("Decision:")
    print_json(decision1)
    print("State:")
    print_json(engine.state)
    print()

    print("User: change premise to vegan curry")
    decision2 = engine.step("change premise to vegan curry")
    print("Decision:")
    print_json(decision2)
    print("State after explicit premise change:")
    print_json(engine.state)


if __name__ == "__main__":
    main()
