import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

MODULE_PATH = Path("host_support/observability.py")
REPO_ROOT = Path(__file__).resolve().parents[1]


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


class _VeryLongRepr:
    def __repr__(self) -> str:
        return "x" * 250


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


def test_build_trace_uses_unknown_kind_when_missing() -> None:
    module = _load_module()
    output = module.build_trace(
        original_input="hello",
        compiler_input="hello",
        decision={},
        state_before={},
        state_after={},
    )

    assert "decision kind: unknown" in output


def test_build_trace_uses_unknown_kind_when_invalid_object_kind() -> None:
    module = _load_module()
    output = module.build_trace(
        original_input="hello",
        compiler_input="hello",
        decision={"kind": 42},
        state_before={},
        state_after={},
    )

    assert "decision kind: unknown" in output


def test_build_trace_reports_added_mapping_keys() -> None:
    module = _load_module()
    output = module.build_trace(
        original_input="hello",
        compiler_input="hello",
        decision={"kind": "update"},
        state_before={"a": 1},
        state_after={"a": 1, "b": 2},
    )

    assert "state change:" in output
    assert "added=['b']" in output


def test_build_trace_reports_removed_mapping_keys() -> None:
    module = _load_module()
    output = module.build_trace(
        original_input="hello",
        compiler_input="hello",
        decision={"kind": "update"},
        state_before={"a": 1, "b": 2},
        state_after={"a": 1},
    )

    assert "state change:" in output
    assert "removed=['b']" in output


def test_build_trace_suppresses_whitespace_only_preprocessor_output() -> None:
    module = _load_module()
    output = module.build_trace(
        original_input="hello",
        compiler_input="hello",
        preprocessor_output="   \n\t  ",
        decision={"kind": "passthrough"},
        state_before={},
        state_after={},
    )

    assert "preprocessor output:" not in output


def test_build_trace_non_mapping_states_render_safely() -> None:
    module = _load_module()
    output = module.build_trace(
        original_input="hello",
        compiler_input="hello",
        decision={"kind": "passthrough"},
        state_before=["docker"],
        state_after=["docker", "kubectl"],
    )

    assert "state change:" in output
    assert "->" in output
    assert "['docker']" in output
    assert "['docker', 'kubectl']" in output


def test_host_support_exports_build_trace() -> None:
    sys.path.insert(0, str(REPO_ROOT))
    sys.modules.pop("host_support", None)
    from host_support import build_trace

    output = build_trace(
        original_input="hello",
        compiler_input="hello",
        decision={"kind": "passthrough"},
        state_before={},
        state_after={},
    )

    assert "Context Compiler trace" in output


def test_build_trace_state_summary_uses_none_fallback_path() -> None:
    module = _load_module()
    output = module.build_trace(
        original_input="hello",
        compiler_input="hello",
        decision={"kind": "passthrough"},
        state_before=None,
        state_after=["docker"],
    )

    assert "state change: none -> ['docker']" in output


def test_build_trace_state_summary_uses_mapping_fallback_path() -> None:
    module = _load_module()
    output = module.build_trace(
        original_input="hello",
        compiler_input="hello",
        decision={"kind": "passthrough"},
        state_before={"b": 2, "a": 1},
        state_after=["docker"],
    )

    assert "state change: dict keys=['a', 'b'] -> ['docker']" in output


def test_build_trace_state_summary_truncates_very_long_repr() -> None:
    module = _load_module()
    output = module.build_trace(
        original_input="hello",
        compiler_input="hello",
        decision={"kind": "passthrough"},
        state_before=_VeryLongRepr(),
        state_after=["docker"],
    )

    assert "state change:" in output
    assert "..." in output


def test_build_compact_trace_text_update_shape() -> None:
    module = _load_module()
    output = module.build_compact_trace_text(
        decision={"kind": "update"},
        state_before={"premise": None, "policies": {}, "version": 2},
        state_after={
            "premise": "concise replies",
            "policies": {"docker": "use"},
            "version": 2,
        },
        llm_called=False,
        state_injected="yes",
    )

    assert output.startswith("Context Compiler trace\n\ndecision kind: update\n")
    assert 'state change: +premise "concise replies", +use docker' in output
    assert 'active state: premise="concise replies"; use docker' in output
    assert "downstream LLM call: no" in output
    assert output.endswith("state injected: yes")


def test_build_compact_trace_text_clarify_shape() -> None:
    module = _load_module()
    output = module.build_compact_trace_text(
        decision={"kind": "clarify", "prompt_to_user": "Use what item?"},
        state_before={"premise": None, "policies": {}, "version": 2},
        state_after={"premise": None, "policies": {}, "version": 2},
        llm_called=False,
        state_injected="no",
    )

    assert output.startswith("Context Compiler trace\n\ndecision kind: clarify\n")
    assert "clarification prompt: Use what item?" in output
    assert "active state: none" in output
    assert "downstream LLM call: no" in output
    assert output.endswith("state injected: no")
