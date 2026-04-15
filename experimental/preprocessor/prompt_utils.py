"""Prompt rendering utilities for experimental preprocessor integrations."""

from pathlib import Path

from context_compiler import State, get_policy_items, get_premise_value

from .constants import PROMPT_TOKEN_NULL_OR_VALUE, PROMPT_TOKEN_POLICY_SET


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
    """Render a state-aware preprocessor prompt from a template file.

    Args:
        path: Prompt template path.
        state: Current compiler state used for token replacement.

    Returns:
        The rendered prompt text, or None when the prompt file cannot be loaded.

    Notes:
        Rendering is intentionally narrow and deterministic:
        - leading # header lines and leading blank lines are removed
        - <NULL_OR_VALUE> becomes null or current premise
        - <SET OF CURRENT POLICY ITEMS> becomes sorted policy keys or "(none)"
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

    rendered = template.replace(PROMPT_TOKEN_NULL_OR_VALUE, premise_value)
    rendered = rendered.replace(PROMPT_TOKEN_POLICY_SET, policies_value)
    return rendered
