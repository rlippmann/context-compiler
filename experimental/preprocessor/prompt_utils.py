"""Prompt rendering utilities for experimental preprocessor integrations."""

from pathlib import Path

from context_compiler import State, get_policy_items, get_premise_value


def _strip_leading_headers(prompt_template: str) -> str:
    """Remove leading blank/comment header lines from a prompt template."""
    lines = prompt_template.splitlines()
    start = 0
    while start < len(lines):
        line = lines[start]
        stripped = line.strip()
        if not stripped or line.lstrip().startswith("#"):
            start += 1
            continue
        break
    return "\n".join(lines[start:])


def render_prompt(path: Path, state: State) -> str | None:
    """Render a state-aware preprocessor prompt from path.

    Behavior is intentionally narrow and deterministic:
    - read prompt text from path
    - drop leading # comment header lines and leading blank lines
    - replace tokens:
      - <NULL_OR_VALUE> -> null or current premise string
      - <SET OF CURRENT POLICY ITEMS> -> sorted policy keys joined by ", " or "(none)"
    - return None if the file cannot be loaded
    """
    try:
        prompt_template = path.read_text(encoding="utf-8")
    except OSError:
        return None

    template = _strip_leading_headers(prompt_template)

    premise = get_premise_value(state)
    premise_value = "null" if premise is None else premise

    all_policy_items = sorted(
        set(get_policy_items(state, "use")) | set(get_policy_items(state, "prohibit"))
    )
    policies_value = ", ".join(all_policy_items) if all_policy_items else "(none)"

    rendered = template.replace("<NULL_OR_VALUE>", premise_value)
    rendered = rendered.replace("<SET OF CURRENT POLICY ITEMS>", policies_value)
    return rendered
