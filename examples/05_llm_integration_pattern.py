"""Example 5: host integration pattern using Decision API."""

from _util import print_decision_summary, print_state_summary

from context_compiler import (
    Engine,
    State,
    create_engine,
    get_decision_state,
    get_error_message,
    is_error,
    is_no_directive,
    is_update,
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

    if is_no_directive(decision):
        print("Host action: no_directive -> core recognized no canonical directive")
        print("Host choice in this example: call fake_llm() without state")
        fake_llm(None, engine_input)
    elif is_update(decision):
        print("Host action: update -> call fake_llm() with compiled state")
        fake_llm(get_decision_state(decision), engine_input)
    elif is_error(decision):
        print("Host action: error -> show prompt, DO NOT call LLM")
        print("error message:", get_error_message(decision))
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
