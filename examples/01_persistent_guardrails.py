"""Example 1: persistent guardrails across turns."""

from _util import print_decision_summary, print_engine_observations

from context_compiler import Engine, create_engine


def build_prompt(engine: Engine, user_input: str) -> str:
    prohibit = sorted(item for item, value in engine.policies.items() if value == "prohibit")
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
    print_engine_observations(
        premise=engine.premise,
        policies=engine.policies,
        label="state after turn 1",
    )
    print()

    print("User: how should I make this curry?")
    decision2 = engine.step("how should I make this curry?")
    print_decision_summary(decision2)
    print_engine_observations(
        premise=engine.premise,
        policies=engine.policies,
        label="state after turn 2",
    )
    print()

    print("Host prompt construction with persisted policy:")
    prompt = build_prompt(engine, "how should I make this curry?")
    print(prompt)


if __name__ == "__main__":
    main()
