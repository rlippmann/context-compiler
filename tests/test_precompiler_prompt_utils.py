from pathlib import Path

from context_compiler import create_engine
from context_compiler.engine import State
from experimental.preprocessor.constants import PROMPT_TOKEN_NULL_OR_VALUE, PROMPT_TOKEN_POLICY_SET
from experimental.preprocessor.prompt_utils import render_prompt


def _write_prompt(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def _empty_state() -> State:
    return create_engine().state


def _populated_state() -> State:
    engine = create_engine()
    engine.step("set premise concise replies")
    engine.step("use zeta")
    engine.step("use beta")
    engine.step("prohibit alpha")
    return engine.state


def test_render_prompt_returns_none_when_file_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"
    assert render_prompt(missing, _empty_state()) is None


def test_render_prompt_strips_leading_header_comments_and_blank_lines(tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.txt"
    _write_prompt(
        prompt_file,
        "\n# header one\n  # header two\n\n"
        f"premise={PROMPT_TOKEN_NULL_OR_VALUE}\n"
        f"policies={PROMPT_TOKEN_POLICY_SET}\n",
    )

    rendered = render_prompt(prompt_file, _empty_state())
    assert rendered is not None
    assert rendered.startswith("premise=null\n")
    assert "# header" not in rendered


def test_render_prompt_replaces_tokens_for_empty_state(tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.txt"
    _write_prompt(
        prompt_file,
        f"premise={PROMPT_TOKEN_NULL_OR_VALUE}\npolicies={PROMPT_TOKEN_POLICY_SET}\n",
    )

    rendered = render_prompt(prompt_file, _empty_state())
    assert rendered == "premise=null\npolicies=(none)"


def test_render_prompt_replaces_tokens_for_populated_state_with_sorted_policy_keys(
    tmp_path: Path,
) -> None:
    prompt_file = tmp_path / "prompt.txt"
    _write_prompt(
        prompt_file,
        f"premise={PROMPT_TOKEN_NULL_OR_VALUE}\npolicies={PROMPT_TOKEN_POLICY_SET}\n",
    )

    rendered = render_prompt(prompt_file, _populated_state())
    assert rendered == "premise=concise replies\npolicies=alpha, beta, zeta"
