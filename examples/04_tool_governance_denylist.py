"""Example 4: host-side tool governance using prohibit policy items."""

from dataclasses import dataclass

from _util import print_decision_summary, print_engine_observations

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

    user_input = "prohibit docker"
    print(f"User: {user_input}")
    decision = engine.step(user_input)
    print_decision_summary(decision)
    print_engine_observations(
        premise=engine.premise,
        policies=engine.policies,
        label="state after turn",
    )
    print()

    print("Host-side tool denylist behavior:")
    prohibit = sorted(item for item, value in engine.policies.items() if value == "prohibit")
    tools = [Tool("docker"), Tool("kubectl")]
    for tool in tools:
        if tool.name in prohibit:
            block_tool(tool)
        else:
            allow_tool(tool)


if __name__ == "__main__":
    main()
