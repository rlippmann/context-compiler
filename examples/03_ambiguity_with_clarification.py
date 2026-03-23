"""Example 3: contradiction clarify flow with host-side blocking."""

from _util import print_json

from context_compiler import create_engine


def fake_llm(user_input: str) -> str:
    print(f"LLM would be called with user_input={user_input!r}")
    return "[example LLM response]"


def main() -> None:
    engine = create_engine()

    print("User: don't use peanuts")
    decision1 = engine.step("don't use peanuts")
    print("Decision:")
    print_json(decision1)
    print()

    print("User: use peanuts")
    decision2 = engine.step("use peanuts")
    print("Decision:")
    print_json(decision2)
    print()

    if decision2["kind"] == "clarify":
        print("Host behavior: clarification pending, do NOT call LLM.")
        print(f"Prompt to user: {decision2['prompt_to_user']}")
    else:
        fake_llm("use peanuts")
    print()

    print("User: clear state")
    decision3 = engine.step("clear state")
    print("Decision:")
    print_json(decision3)
    print("State after explicit reset:")
    print_json(engine.state)


if __name__ == "__main__":
    main()
