"""Example 3: contradiction clarify flow with host-side blocking."""

from context_compiler import create_engine
from examples._util import print_decision_summary, print_state_summary


def fake_llm(user_input: str) -> str:
    print(f"LLM would be called with user_input={user_input!r}")
    return "[example LLM response]"


def main() -> None:
    engine = create_engine()

    print("User: prohibit peanuts")
    decision1 = engine.step("prohibit peanuts")
    print_decision_summary(decision1)
    print()

    print("User: use peanuts")
    decision2 = engine.step("use peanuts")
    print_decision_summary(decision2)
    print()

    if decision2["kind"] == "clarify":
        print("Host behavior: clarification pending, do NOT call LLM.")
        print(f"Clarify prompt: {decision2['prompt_to_user']}")
    else:
        fake_llm("use peanuts")
    print()

    print("User: clear state")
    decision3 = engine.step("clear state")
    print_decision_summary(decision3)
    print_state_summary(engine.state, "state after explicit reset")


if __name__ == "__main__":
    main()
