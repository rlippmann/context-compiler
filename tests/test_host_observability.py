import importlib.util
from dataclasses import dataclass
from pathlib import Path

MODULE_PATH = Path("host_support/observability.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("host_support_observability_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load host_support/observability.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass
class _DecisionObject:
    kind: str
    prompt_to_user: str | None = None


def test_build_trace_passthrough_without_preprocessor_output() -> None:
    module = _load_module()
    output = module.build_trace(
        original_input="hello",
        compiler_input="hello",
        decision={"kind": "passthrough"},
        state_before={},
        state_after={},
        llm_called=True,
    )

    assert "original input: hello" in output
    assert "compiler input: hello" in output
    assert "decision kind: passthrough" in output
    assert "state change: unchanged" in output
    assert "downstream LLM call: yes" in output
    assert "preprocessor output:" not in output


def test_build_trace_update_with_changed_state() -> None:
    module = _load_module()
    output = module.build_trace(
        original_input="use docker",
        compiler_input="use docker",
        decision={"kind": "update"},
        state_before={"allowed_tools": []},
        state_after={"allowed_tools": ["docker"]},
        llm_called=False,
    )

    assert "decision kind: update" in output
    assert "state change:" in output
    assert "changed=['allowed_tools']" in output
    assert "downstream LLM call: no" in output


def test_build_trace_clarify_includes_prompt() -> None:
    module = _load_module()
    output = module.build_trace(
        original_input="use",
        compiler_input="use",
        decision=_DecisionObject(kind="clarify", prompt_to_user="Use what item?"),
        state_before={"pending": None},
        state_after={"pending": None},
        llm_called=False,
    )

    assert "decision kind: clarify" in output
    assert "clarification prompt: Use what item?" in output
    assert "downstream LLM call: no" in output


def test_build_trace_includes_preprocessor_output_when_present() -> None:
    module = _load_module()
    output = module.build_trace(
        original_input="pls use docker",
        compiler_input="use docker",
        preprocessor_output="use docker",
        decision={"kind": "update"},
        state_before={"allowed_tools": []},
        state_after={"allowed_tools": ["docker"]},
    )

    assert "preprocessor output: use docker" in output
    assert "decision kind: update" in output


def test_build_trace_handles_none_states_defensively() -> None:
    module = _load_module()
    output = module.build_trace(
        original_input="hello",
        compiler_input="hello",
        decision={"kind": "passthrough"},
        state_before=None,
        state_after=None,
    )

    assert "state change: none -> none" in output
    assert "downstream LLM call: no" in output
