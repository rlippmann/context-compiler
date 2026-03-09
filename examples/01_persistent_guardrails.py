"""Example 1: persistent guardrails across turns."""

from _util import print_json

from context_compiler import State, create_engine


def build_prompt(state: State, user_input: str) -> str:
    prohibit = state["policies"]["prohibit"]
    prohibit_text = ", ".join(prohibit) if prohibit else "(none)"
    return (
        "System: Follow authoritative conversation state.\n"
        "Compiled context:\n"
        f"- policies.prohibit: {prohibit_text}\n"
        f"User: {user_input}"
    )


def main() -> None:
    engine = create_engine()

    print("User: don't use docker")
    decision1 = engine.step("don't use docker")
    print("Decision:")
    print_json(decision1)
    print("State after turn 1:")
    print_json(engine.state)
    print()

    print("User: how should I deploy my service?")
    decision2 = engine.step("how should I deploy my service?")
    print("Decision:")
    print_json(decision2)
    print("State after turn 2:")
    print_json(engine.state)
    print()

    print("Host prompt construction with persisted policy:")
    prompt = build_prompt(engine.state, "how should I deploy my service?")
    print(prompt)


if __name__ == "__main__":
    main()
