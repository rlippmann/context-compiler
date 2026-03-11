"""Example 3: ambiguous directive flow with clarification handling."""

from _util import print_json

from context_compiler import create_engine


def fake_llm(user_input: str) -> str:
    print(f"LLM would be called with user_input={user_input!r}")
    return "[example LLM response]"


def main() -> None:
    engine = create_engine()

    print("User: no use peanuts")
    decision1 = engine.step("no use peanuts")
    print("Decision:")
    print_json(decision1)
    print()

    if decision1["kind"] == "clarify":
        print("Host behavior: clarification pending, do NOT call LLM.")
        print(f"Prompt to user: {decision1['prompt_to_user']}")
    else:
        fake_llm("no use peanuts")
    print()

    print("User: yes")
    decision2 = engine.step("yes")
    print("Decision:")
    print_json(decision2)
    print("State after clarification acceptance:")
    print_json(engine.state)


if __name__ == "__main__":
    main()
