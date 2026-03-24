"""Example 4: host-side tool governance using prohibit policy items."""

from dataclasses import dataclass

from _util import print_decision_summary, print_state_summary

from context_compiler import create_engine, get_policy_items


@dataclass
class Tool:
    name: str


def block_tool(tool: Tool) -> None:
    print(f"Blocked tool: {tool.name}")


def allow_tool(tool: Tool) -> None:
    print(f"Allowed tool: {tool.name}")


def main() -> None:
    engine = create_engine()

    user_input = "prohibit docker"
    print(f"User: {user_input}")
    decision = engine.step(user_input)
    print_decision_summary(decision)
    state = engine.state
    print_state_summary(state, "state after turn")
    print()

    print("Host-side tool denylist behavior:")
    prohibit = get_policy_items(state, "prohibit")
    tools = [Tool("docker"), Tool("kubectl")]
    for tool in tools:
        if tool.name in prohibit:
            block_tool(tool)
        else:
            allow_tool(tool)


if __name__ == "__main__":
    main()
