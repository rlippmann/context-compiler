import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from demos.common import consume_last_report  # noqa: E402


def _load_demo_module(filename: str) -> ModuleType:
    module_name = f"test_demo_behavior_{filename[:-3]}"
    module_path = REPO_ROOT / "demos" / filename
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sequenced_outputs(outputs: list[str]) -> Callable[[object], str]:
    queue = list(outputs)

    def _fake_complete_messages(_messages: object) -> str:
        if not queue:
            raise AssertionError("No mocked LLM output remaining for this call.")
        return queue.pop(0)

    return _fake_complete_messages


def test_demo_08_reports_invalid_replacement_block_and_unchanged_state(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_demo_module("08_llm_replacement_precondition.py")
    monkeypatch.setattr(
        module,
        "complete_messages",
        _sequenced_outputs(
            [
                "ACTION:proceed\nLooks fine.",
                "ACTION:proceed\nSeems acceptable.",
            ]
        ),
    )

    module.main()
    output = capsys.readouterr().out
    report = consume_last_report()

    assert report is not None
    assert report["name"].startswith("08_replacement_precondition")
    assert report["baseline_pass"] is False
    assert report["reinjected_state_pass"] is False
    assert report["compiler_pass"] is False
    assert report["compiler_compact_pass"] is True
    assert report["demo_pass"] is False
    assert "baseline: FAIL" in output
    assert "reinjected-state: FAIL" in output
    assert "compiler: FAIL" in output


def test_demo_08_reinjected_path_does_not_instantiate_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_demo_module("08_llm_replacement_precondition.py")

    original_create_engine = module.create_engine

    class _EngineWrapper:
        reinjected_seen = False

        def __init__(self, inner: object) -> None:
            self._inner = inner

        def __getattr__(self, name: str) -> object:
            return getattr(self._inner, name)

        def step(self, text: str) -> dict[str, object]:
            if text == module.USER_INPUT:
                _EngineWrapper.reinjected_seen = False
            return self._inner.step(text)

    engine = _EngineWrapper(original_create_engine())

    monkeypatch.setattr(module, "create_engine", lambda: engine)

    original_build_reinjected_messages = module.build_reinjected_messages

    def wrapped_build_reinjected_messages(*args: object, **kwargs: object):
        _EngineWrapper.reinjected_seen = True
        return original_build_reinjected_messages(*args, **kwargs)

    monkeypatch.setattr(module, "build_reinjected_messages", wrapped_build_reinjected_messages)
    monkeypatch.setattr(module, "complete_messages", _sequenced_outputs(["x", "y"]))

    module.main()
    report = consume_last_report()

    assert _EngineWrapper.reinjected_seen is True
    assert report is not None
    assert report["reinjected_state_pass"] is False


def test_demo_09_reports_invalid_replacement_non_pending_boundary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_demo_module("09_llm_pending_clarification.py")
    monkeypatch.setattr(
        module,
        "complete_messages",
        _sequenced_outputs(
            [
                "STATE_MACHINE:plausible\nNarrative only.",
                "STATE_MACHINE:plausible\nNarrative only.",
            ]
        ),
    )

    module.main()
    output = capsys.readouterr().out
    report = consume_last_report()

    assert report is not None
    assert report["name"].startswith("09_pending_clarification_boundary")
    assert report["baseline_pass"] is False
    assert report["reinjected_state_pass"] is False
    assert report["compiler_pass"] is True
    assert report["compiler_compact_pass"] is True
    assert report["demo_pass"] is True
    assert "reinjected-state: FAIL" in output
    assert "compiler: PASS" in output


def test_demo_09_reinjected_path_does_not_call_create_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_demo_module("09_llm_pending_clarification.py")

    original_create_engine = module.create_engine
    create_engine_calls = 0

    def wrapped_create_engine() -> object:
        nonlocal create_engine_calls
        create_engine_calls += 1
        return original_create_engine()

    monkeypatch.setattr(module, "create_engine", wrapped_create_engine)
    monkeypatch.setattr(module, "complete_messages", _sequenced_outputs(["x", "y"]))

    module.main()
    report = consume_last_report()

    assert create_engine_calls == 1
    assert report is not None
    assert report["reinjected_state_pass"] is False
