"""Example 1: persistent guardrails across turns."""

from context_compiler import State, create_engine, get_policy_items
from examples._util import print_decision_summary, print_state_summary


def build_prompt(state: State, user_input: str) -> str:
    prohibit = get_policy_items(state, "prohibit")
    prohibit_text = ", ".join(prohibit) if prohibit else "(none)"
    return (
        "System: Follow authoritative conversation state.\n"
        "Compiled context:\n"
        f"- prohibited policy items: {prohibit_text}\n"
        f"User: {user_input}"
    )


def main() -> None:
    engine = create_engine()

    print("User: prohibit peanuts")
    decision1 = engine.step("prohibit peanuts")
    print_decision_summary(decision1)
    print_state_summary(engine.state, "state after turn 1")
    print()

    print("User: how should I make this curry?")
    decision2 = engine.step("how should I make this curry?")
    print_decision_summary(decision2)
    print_state_summary(engine.state, "state after turn 2")
    print()

    print("Host prompt construction with persisted policy:")
    prompt = build_prompt(engine.state, "how should I make this curry?")
    print(prompt)


if __name__ == "__main__":
    main()
