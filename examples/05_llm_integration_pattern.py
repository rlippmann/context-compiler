"""Example 5: host integration pattern using Decision API."""

from collections.abc import Mapping

from _util import print_decision_summary, print_engine_observations

from context_compiler import (
    Engine,
    NoDirectiveDecision,
    SemanticErrorDecision,
    UpdateDecision,
)


def fake_llm(state: tuple[str | None, Mapping[str, str]] | None, user_input: str) -> str:
    print("LLM would be called with:")
    if state is None:
        print("state: (none)")
    else:
        premise, policies = state
        print_engine_observations(premise=premise, policies=policies)
    print("user_input:", user_input)
    return "[example LLM response]"


def handle_turn(engine_input: str, engine: Engine) -> None:
    decision = engine.step(engine_input)
    print(f"User: {engine_input}")
    print_decision_summary(decision)

    if isinstance(decision, NoDirectiveDecision):
        # Ordinary input stays host-managed; this example forwards it to the model unchanged.
        print("Host action: no_directive -> core recognized no canonical directive")
        print("Host choice in this example: call fake_llm() without state")
        fake_llm(None, engine_input)
    elif isinstance(decision, UpdateDecision):
        # Successful directives produce authoritative state that host code can pass downstream.
        print("Host action: update -> call fake_llm() with compiled state")
        fake_llm((engine.premise, engine.policies), engine_input)
    elif isinstance(decision, SemanticErrorDecision):
        print("Host action: error -> show prompt, DO NOT call LLM")
        print("error message:", decision.message)
    print()


def main() -> None:
    engine = Engine()

    handle_turn("hello there", engine)
    handle_turn("set premise concise replies", engine)
    handle_turn("prohibit peanuts", engine)
    handle_turn("remove policy peanuts", engine)
    handle_turn("use peanuts", engine)
    handle_turn("clear state", engine)


if __name__ == "__main__":
    main()
