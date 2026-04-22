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


def test_example_06_wires_compile_and_apply_replay_entry_points(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_example_module("06_transcript_replay.py")
    original_compile = module.compile_transcript
    original_create_engine = module.create_engine
    compile_calls: list[list[dict[str, str]]] = []
    apply_calls: list[list[dict[str, str]]] = []
    replay_result_kinds: list[str] = []

    def compile_wrapper(transcript: list[dict[str, str]]) -> object:
        compile_calls.append(transcript)
        result = original_compile(transcript)
        assert isinstance(result, dict)
        kind = result.get("kind")
        assert isinstance(kind, str)
        replay_result_kinds.append(kind)
        return result

    def create_engine_wrapper() -> object:
        engine = original_create_engine()
        original_apply = engine.apply_transcript

        def apply_wrapper(transcript: list[dict[str, str]]) -> object:
            apply_calls.append(transcript)
            result = original_apply(transcript)
            assert isinstance(result, dict)
            kind = result.get("kind")
            assert isinstance(kind, str)
            replay_result_kinds.append(kind)
            return result

        engine.apply_transcript = apply_wrapper  # type: ignore[assignment]
        return engine

    monkeypatch.setattr(module, "compile_transcript", compile_wrapper)
    monkeypatch.setattr(module, "create_engine", create_engine_wrapper)

    module.main()
    output = capsys.readouterr().out

    assert "Replay from fresh engine (compile_transcript):" in output
    assert "Replay onto current engine (engine.apply_transcript):" in output
    assert len(compile_calls) == 1
    assert len(apply_calls) == 1
    assert replay_result_kinds == ["state", "state"]
