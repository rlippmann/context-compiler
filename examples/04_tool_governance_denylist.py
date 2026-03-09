"""Example 4: host-side tool governance using policies.prohibit denylist."""

from dataclasses import dataclass

from _util import print_json

from context_compiler import create_engine


@dataclass
class Tool:
    name: str


def block_tool(tool: Tool) -> None:
    print(f"Blocked tool: {tool.name}")


def allow_tool(tool: Tool) -> None:
    print(f"Allowed tool: {tool.name}")


def main() -> None:
    engine = create_engine()

    user_input = "don't use docker"
    print(f"User: {user_input}")
    decision = engine.step(user_input)
    print("Decision:")
    print_json(decision)
    print("State after turn:")
    state = engine.state
    print_json(state)
    print()

    print("Host-side tool denylist behavior:")
    tools = [Tool("docker"), Tool("kubectl")]
    for tool in tools:
        if tool.name in state["policies"]["prohibit"]:
            block_tool(tool)
        else:
            allow_tool(tool)


if __name__ == "__main__":
    main()
