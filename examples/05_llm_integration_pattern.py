"""Example 5: host integration pattern using Decision API."""

from _util import print_decision_summary, print_state_summary

from context_compiler import (
    DECISION_CLARIFY,
    DECISION_PASSTHROUGH,
    DECISION_UPDATE,
    Engine,
    State,
    create_engine,
)


def fake_llm(state: State | None, user_input: str) -> str:
    print("LLM would be called with:")
    if state is None:
        print("state: (none)")
    else:
        print_state_summary(state)
    print("user_input:", user_input)
    return "[example LLM response]"


def handle_turn(engine_input: str, engine: Engine) -> None:
    decision = engine.step(engine_input)
    print(f"User: {engine_input}")
    print_decision_summary(decision)

    if decision["kind"] == DECISION_PASSTHROUGH:
        print("Host action: passthrough -> call fake_llm() without state")
        fake_llm(None, engine_input)
    elif decision["kind"] == DECISION_UPDATE:
        print("Host action: update -> call fake_llm() with compiled state")
        fake_llm(decision["state"], engine_input)
    elif decision["kind"] == DECISION_CLARIFY:
        print("Host action: clarify -> show prompt, DO NOT call LLM")
        print("clarify prompt:", decision["prompt_to_user"])
    print()


def main() -> None:
    engine = create_engine()

    handle_turn("hello there", engine)
    handle_turn("set premise concise replies", engine)
    handle_turn("prohibit peanuts", engine)
    handle_turn("remove policy peanuts", engine)
    handle_turn("use peanuts", engine)
    handle_turn("clear state", engine)


if __name__ == "__main__":
    main()
