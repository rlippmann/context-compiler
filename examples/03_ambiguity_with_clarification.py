"""Example 3: contradiction clarify flow with host-side blocking."""

from _util import print_decision_summary, print_state_summary

from context_compiler import create_engine, get_clarify_prompt, is_clarify


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

    if is_clarify(decision2):
        print("Host behavior: clarification pending, do NOT call LLM.")
        print(f"Clarify prompt: {get_clarify_prompt(decision2)}")
    else:
        fake_llm("use peanuts")
    print()

    print("User: clear state")
    decision3 = engine.step("clear state")
    print_decision_summary(decision3)
    print_state_summary(engine.state, "state after explicit reset")


if __name__ == "__main__":
    main()
