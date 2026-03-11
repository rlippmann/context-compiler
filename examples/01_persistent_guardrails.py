"""Example 1: persistent guardrails across turns."""

from _util import print_json

from context_compiler import State, create_engine
from context_compiler.const import POLICY_PROHIBIT, STATE_POLICIES


def build_prompt(state: State, user_input: str) -> str:
    prohibit = state[STATE_POLICIES][POLICY_PROHIBIT]
    prohibit_text = ", ".join(prohibit) if prohibit else "(none)"
    return (
        "System: Follow authoritative conversation state.\n"
        "Compiled context:\n"
        f"- policies.prohibit: {prohibit_text}\n"
        f"User: {user_input}"
    )


def main() -> None:
    engine = create_engine()

    print("User: don't use peanuts")
    decision1 = engine.step("don't use peanuts")
    print("Decision:")
    print_json(decision1)
    print("State after turn 1:")
    print_json(engine.state)
    print()

    print("User: how should I make this curry?")
    decision2 = engine.step("how should I make this curry?")
    print("Decision:")
    print_json(decision2)
    print("State after turn 2:")
    print_json(engine.state)
    print()

    print("Host prompt construction with persisted policy:")
    prompt = build_prompt(engine.state, "how should I make this curry?")
    print(prompt)


if __name__ == "__main__":
    main()
