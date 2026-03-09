"""Example 5: host integration pattern using Decision API."""

from _util import canonical_json, print_json

from context_compiler import Engine, State, create_engine


def fake_llm(state: State | None, user_input: str) -> str:
    print("LLM would be called with:")
    print(f"state: {canonical_json(state)}")
    print("user_input:", user_input)
    return "[example LLM response]"


def handle_turn(engine_input: str, engine: Engine) -> None:
    decision = engine.step(engine_input)
    print(f"User: {engine_input}")
    print("Decision:")
    print_json(decision)

    if decision["kind"] == "passthrough":
        print("Host action: passthrough -> call fake_llm() without state")
        fake_llm(None, engine_input)
    elif decision["kind"] == "update":
        print("Host action: update -> call fake_llm() with compiled state")
        fake_llm(decision["state"], engine_input)
    elif decision["kind"] == "clarify":
        print("Host action: clarify -> show prompt, DO NOT call LLM")
        print("prompt_to_user:", decision["prompt_to_user"])
    print()


def main() -> None:
    engine = create_engine()

    handle_turn("hello there", engine)
    handle_turn("don't use docker", engine)
    handle_turn("no use kubernetes", engine)
    handle_turn("yes", engine)


if __name__ == "__main__":
    main()
