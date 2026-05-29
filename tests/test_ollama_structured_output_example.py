import importlib.util
from pathlib import Path

from context_compiler import create_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PATH = REPO_ROOT / "examples" / "integrations" / "ollama_structured_output" / "example.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ollama_structured_output_example", EXAMPLE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_use_python_script_selects_python_schema() -> None:
    module = _load_module()
    engine = create_engine()

    first = engine.step("use python_script")
    assert first["kind"] == "update"

    plan = module.plan_turn("write script", engine)
    assert plan["selected_schema_item"] == "python_script"
    assert plan["format_schema"] == module.PYTHON_SCRIPT_SCHEMA


def test_prohibit_shell_command_does_not_select_shell_schema() -> None:
    module = _load_module()
    engine = create_engine()

    assert engine.step("use python_script")["kind"] == "update"
    assert engine.step("prohibit shell_command")["kind"] == "update"

    plan = module.plan_turn("do task", engine)
    assert plan["selected_schema_item"] == "python_script"
    assert plan["format_schema"] != module.SHELL_COMMAND_SCHEMA


def test_unknown_or_no_matching_state_selects_no_schema() -> None:
    module = _load_module()
    engine = create_engine()

    plan = module.plan_turn("hello", engine)
    assert plan["decision_kind"] == "passthrough"
    assert plan["selected_schema_item"] is None
    assert plan["format_schema"] is None


def test_contradictory_input_is_compiler_clarify_not_host_resolution() -> None:
    module = _load_module()
    engine = create_engine()

    assert engine.step("use python_script")["kind"] == "update"
    conflict_plan = module.plan_turn("prohibit python_script", engine)
    assert conflict_plan["decision_kind"] == "clarify"
    assert conflict_plan["selected_schema_item"] is None
    assert conflict_plan["format_schema"] is None
