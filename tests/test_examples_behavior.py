import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(EXAMPLES_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLES_DIR))

pytestmark = pytest.mark.contract


def _load_example_module(filename: str) -> ModuleType:
    module_name = f"test_examples_behavior_{filename[:-3]}"
    module_path = EXAMPLES_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_example_03_clarify_gate_blocks_llm_and_allows_later_update(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_example_module("03_ambiguity_with_clarification.py")
    decision_kinds: list[str] = []
    llm_calls: list[str] = []

    def capture_decision_summary(decision: object) -> None:
        assert isinstance(decision, dict)
        kind = decision.get("kind")
        assert isinstance(kind, str)
        decision_kinds.append(kind)

    def fake_llm(user_input: str) -> str:
        llm_calls.append(user_input)
        return "[test llm output]"

    monkeypatch.setattr(module, "print_decision_summary", capture_decision_summary)
    monkeypatch.setattr(module, "fake_llm", fake_llm)

    module.main()
    output = capsys.readouterr().out

    assert decision_kinds == ["update", "clarify", "update"]
    assert "Host behavior: clarification pending, do NOT call LLM." in output
    assert llm_calls == []


def test_example_04_tool_governance_blocks_and_allows_expected_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_example_module("04_tool_governance_denylist.py")
    blocked_tools: list[str] = []
    allowed_tools: list[str] = []

    def capture_block(tool: object) -> None:
        assert hasattr(tool, "name")
        blocked_tools.append(str(tool.name))

    def capture_allow(tool: object) -> None:
        assert hasattr(tool, "name")
        allowed_tools.append(str(tool.name))

    monkeypatch.setattr(module, "block_tool", capture_block)
    monkeypatch.setattr(module, "allow_tool", capture_allow)

    module.main()

    assert blocked_tools == ["docker"]
    assert allowed_tools == ["kubectl"]


def test_example_05_dispatches_passthrough_update_and_clarify_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_example_module("05_llm_integration_pattern.py")
    engine = module.create_engine()
    decision_kinds: list[str] = []
    llm_calls: list[tuple[object, str]] = []

    def capture_decision_summary(decision: object) -> None:
        assert isinstance(decision, dict)
        kind = decision.get("kind")
        assert isinstance(kind, str)
        decision_kinds.append(kind)

    def capture_fake_llm(state: object, user_input: str) -> str:
        llm_calls.append((state, user_input))
        return "[test llm output]"

    monkeypatch.setattr(module, "print_decision_summary", capture_decision_summary)
    monkeypatch.setattr(module, "fake_llm", capture_fake_llm)

    module.handle_turn("hello there", engine)  # passthrough
    module.handle_turn("set premise concise replies", engine)  # update
    calls_before_clarify = len(llm_calls)
    module.handle_turn("set premise verbose replies", engine)  # clarify

    assert decision_kinds == ["passthrough", "update", "clarify"]
    assert len(llm_calls) == calls_before_clarify
    assert llm_calls[0][0] is None
    assert llm_calls[0][1] == "hello there"
    assert llm_calls[1][0] is not None
    assert llm_calls[1][1] == "set premise concise replies"


def test_example_06_sequences_steps_and_restores_checkpoint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_example_module("06_step_sequence_and_checkpoint.py")
    original_create_engine = module.create_engine
    step_calls: list[str] = []
    checkpoint_exports = 0
    checkpoint_imports = 0

    def create_engine_wrapper() -> object:
        nonlocal checkpoint_exports, checkpoint_imports
        engine = original_create_engine()
        original_step = engine.step
        original_export = engine.export_checkpoint_json
        original_import = engine.import_checkpoint_json

        def step_wrapper(user_input: str) -> object:
            step_calls.append(user_input)
            return original_step(user_input)

        def export_wrapper() -> str:
            nonlocal checkpoint_exports
            checkpoint_exports += 1
            return original_export()

        def import_wrapper(payload: str) -> None:
            nonlocal checkpoint_imports
            checkpoint_imports += 1
            original_import(payload)

        engine.step = step_wrapper  # type: ignore[assignment]
        engine.export_checkpoint_json = export_wrapper  # type: ignore[assignment]
        engine.import_checkpoint_json = import_wrapper  # type: ignore[assignment]
        return engine

    monkeypatch.setattr(module, "create_engine", create_engine_wrapper)

    module.main()
    output = capsys.readouterr().out

    assert "Sequence directives through engine.step():" in output
    assert "Checkpoint restore keeps authority state:" in output
    assert step_calls == [
        "prohibit peanuts",
        "set premise vegetarian curry",
        "change premise to vegan curry",
    ]
    assert checkpoint_exports == 1
    assert checkpoint_imports == 1
