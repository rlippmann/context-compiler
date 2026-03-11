import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"


def _run_example(script_name: str) -> str:
    script = EXAMPLES_DIR / script_name
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    return completed.stdout


def _canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def test_persistent_guardrails_example_output() -> None:
    output = _run_example("01_persistent_guardrails.py")

    assert "User: don't use peanuts" in output
    assert (
        _canonical_json(
            {
                "kind": "update",
                "prompt_to_user": None,
                "state": {
                    "facts": {"focus.primary": None},
                    "policies": {"prohibit": ["peanuts"]},
                    "version": 1,
                },
            }
        )
        in output
    )
    assert _canonical_json({"kind": "passthrough", "prompt_to_user": None, "state": None}) in output
    assert (
        _canonical_json(
            {
                "facts": {"focus.primary": None},
                "policies": {"prohibit": ["peanuts"]},
                "version": 1,
            }
        )
        in output
    )
    assert "Compiled context:" in output
    assert "- policies.prohibit: peanuts" in output
    assert "User: how should I make this curry?" in output


def test_configuration_and_correction_example_output() -> None:
    output = _run_example("02_configuration_and_correction.py")

    assert "User: use vegetarian curry" in output
    assert (
        _canonical_json(
            {
                "kind": "update",
                "prompt_to_user": None,
                "state": {
                    "facts": {"focus.primary": "vegetarian curry"},
                    "policies": {"prohibit": []},
                    "version": 1,
                },
            }
        )
        in output
    )
    assert (
        _canonical_json(
            {
                "facts": {"focus.primary": "vegetarian curry"},
                "policies": {"prohibit": []},
                "version": 1,
            }
        )
        in output
    )
    assert "User: actually vegan curry" in output
    assert (
        _canonical_json(
            {
                "kind": "update",
                "prompt_to_user": None,
                "state": {
                    "facts": {"focus.primary": "vegan curry"},
                    "policies": {"prohibit": []},
                    "version": 1,
                },
            }
        )
        in output
    )
    assert (
        _canonical_json(
            {
                "facts": {"focus.primary": "vegan curry"},
                "policies": {"prohibit": []},
                "version": 1,
            }
        )
        in output
    )
    assert "State (last write wins):" in output


def test_ambiguity_with_clarification_example_output() -> None:
    output = _run_example("03_ambiguity_with_clarification.py")

    assert "User: no use peanuts" in output
    assert (
        _canonical_json(
            {
                "kind": "clarify",
                "prompt_to_user": "Did you mean to prohibit 'peanuts'?",
                "state": None,
            }
        )
        in output
    )
    assert "do NOT call LLM" in output
    assert "Prompt to user: Did you mean to prohibit 'peanuts'?" in output
    assert "User: yes" in output
    assert (
        _canonical_json(
            {
                "kind": "update",
                "prompt_to_user": None,
                "state": {
                    "facts": {"focus.primary": None},
                    "policies": {"prohibit": ["peanuts"]},
                    "version": 1,
                },
            }
        )
        in output
    )
    assert (
        _canonical_json(
            {
                "facts": {"focus.primary": None},
                "policies": {"prohibit": ["peanuts"]},
                "version": 1,
            }
        )
        in output
    )


def test_tool_governance_denylist_example_output() -> None:
    output = _run_example("04_tool_governance_denylist.py")

    assert "User: don't use docker" in output
    assert "Decision:" in output
    assert (
        _canonical_json(
            {
                "kind": "update",
                "prompt_to_user": None,
                "state": {
                    "facts": {"focus.primary": None},
                    "policies": {"prohibit": ["docker"]},
                    "version": 1,
                },
            }
        )
        in output
    )
    assert "State after turn:" in output
    assert (
        _canonical_json(
            {
                "facts": {"focus.primary": None},
                "policies": {"prohibit": ["docker"]},
                "version": 1,
            }
        )
        in output
    )
    assert "Host-side tool denylist behavior:" in output
    assert "Blocked tool: docker" in output
    assert "Allowed tool: kubectl" in output


def test_llm_integration_pattern_example_output() -> None:
    output = _run_example("05_llm_integration_pattern.py")
    peanuts_state = {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": ["peanuts"]},
        "version": 1,
    }
    peanuts_shellfish_state = {
        "facts": {"focus.primary": None},
        "policies": {"prohibit": ["peanuts", "shellfish"]},
        "version": 1,
    }

    assert "User: hello there" in output
    assert _canonical_json({"kind": "passthrough", "prompt_to_user": None, "state": None}) in output
    assert "Host action: passthrough -> call fake_llm() without state" in output
    assert "state: null" in output
    assert "User: don't use peanuts" in output
    assert (
        _canonical_json(
            {
                "kind": "update",
                "prompt_to_user": None,
                "state": peanuts_state,
            }
        )
        in output
    )
    assert "Host action: update -> call fake_llm() with compiled state" in output
    assert f"state: {_canonical_json(peanuts_state)}" in output
    assert "User: no use shellfish" in output
    assert (
        _canonical_json(
            {
                "kind": "clarify",
                "prompt_to_user": "Did you mean to prohibit 'shellfish'?",
                "state": None,
            }
        )
        in output
    )
    assert "Host action: clarify -> show prompt, DO NOT call LLM" in output
    assert "User: yes" in output
    assert "prompt_to_user: Did you mean to prohibit 'shellfish'?" in output
    assert (
        _canonical_json(
            {
                "kind": "update",
                "prompt_to_user": None,
                "state": peanuts_shellfish_state,
            }
        )
        in output
    )
    assert f"state: {_canonical_json(peanuts_shellfish_state)}" in output
