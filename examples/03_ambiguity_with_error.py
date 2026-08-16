"""Example 3: contradiction error flow with host-side blocking."""

from _util import print_decision_summary, print_engine_observations

from context_compiler import (
    Engine,
    SemanticErrorDecision,
)


def fake_llm(user_input: str) -> str:
    print(f"LLM would be called with user_input={user_input!r}")
    return "[example LLM response]"


def main() -> None:
    engine = Engine()

    print("User: prohibit peanuts")
    decision1 = engine.step("prohibit peanuts")
    print_decision_summary(decision1)
    print()

    print("User: use peanuts")
    decision2 = engine.step("use peanuts")
    print_decision_summary(decision2)
    print()

    if isinstance(decision2, SemanticErrorDecision):
        print("Host behavior: error returned, do NOT call LLM.")
        print(f"Error message: {decision2.message}")
    else:
        fake_llm("use peanuts")
    print()

    print("User: clear state")
    decision3 = engine.step("clear state")
    print_decision_summary(decision3)
    print_engine_observations(
        premise=engine.premise,
        policies=engine.policies,
        label="state after explicit reset",
    )


if __name__ == "__main__":
    main()
