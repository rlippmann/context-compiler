"""Example 7: explicit single-policy correction without reset policies."""

from _util import print_json

from context_compiler import create_engine


def main() -> None:
    engine = create_engine()

    print("User: prohibit peanuts")
    decision1 = engine.step("prohibit peanuts")
    print("Decision:")
    print_json(decision1)
    print()

    print("User: remove policy peanuts")
    decision2 = engine.step("remove policy peanuts")
    print("Decision:")
    print_json(decision2)
    print()

    print("User: use peanuts")
    decision3 = engine.step("use peanuts")
    print("Decision:")
    print_json(decision3)
    print()

    print("Final state:")
    print_json(engine.state)


if __name__ == "__main__":
    main()
