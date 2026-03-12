import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_demo_module(filename: str) -> ModuleType:
    module_name = f"test_{filename[:-3]}"
    module_path = REPO_ROOT / "demos" / filename
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_selected_tool_prefers_tool_tag() -> None:
    module = _load_demo_module("04_llm_tool_governance.py")
    output = "TOOL:kubectl\nACTION:Use kubectl apply."

    assert module.selected_tool(output) == "kubectl"


def test_selected_tool_falls_back_to_action_line() -> None:
    module = _load_demo_module("04_llm_tool_governance.py")
    output = "- Recommended: choose docker for this deployment."

    assert module.selected_tool(output) == "docker"


def test_selected_tool_uses_regex_fallback_after_unknown_tag() -> None:
    module = _load_demo_module("04_llm_tool_governance.py")
    output = "TOOL:helm\ntool : kubectl"

    assert module.selected_tool(output) == "kubectl"


def test_selected_tool_returns_none_for_unknown_or_missing_tool() -> None:
    module = _load_demo_module("04_llm_tool_governance.py")
    unknown_tag = "TOOL:helm\nACTION:Use helm install."
    missing_tool = "ACTION:Use terraform apply."

    assert module.selected_tool(unknown_tag) is None
    assert module.selected_tool(missing_tool) is None
