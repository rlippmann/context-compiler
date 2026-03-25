import runpy
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from demos import run_demo  # noqa: E402
from demos.common import consume_last_info_report  # noqa: E402
from demos.llm_client import DemoLLMError  # noqa: E402


def _demo_report(*, baseline_pass: bool, compiler_pass: bool) -> run_demo.DemoReport:
    return {
        "name": "01_fake — regression fixture",
        "expected": "expected behavior",
        "actual": "actual behavior",
        "baseline_pass": baseline_pass,
        "compiler_pass": compiler_pass,
        "compiler_compact_pass": compiler_pass,
        "demo_pass": compiler_pass,
    }


def _info_report() -> run_demo.InfoReport:
    return {
        "name": "06_context_compaction — superseded directives eliminated",
        "baseline_context_length": 137,
        "compiled_context_length": 37,
        "context_reduction_percent": 73,
        "baseline_prompt_length": 247,
        "compiled_prompt_length": 160,
        "prompt_reduction_percent": 35,
    }


def test_demo_file_mapping_uses_current_0_5_demo_filenames() -> None:
    assert run_demo.DEMO_FILES == {
        "1": "01_llm_contradiction_clarify.py",
        "2": "02_llm_constraint_guardrail.py",
        "3": "03_llm_premise_guardrail.py",
        "4": "04_llm_tool_denylist_guardrail.py",
        "5": "05_llm_prompt_drift_vs_state.py",
        "6": "06_llm_context_compaction.py",
        "7": "07_llm_prompt_vs_state.py",
    }

    demos_dir = REPO_ROOT / "demos"
    for filename in run_demo.DEMO_FILES.values():
        assert (demos_dir / filename).is_file()


def test_runner_dispatches_selected_demo_to_current_filename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(
        path: Path,
        *,
        verbose: bool,
        llm_delay: float,
        demo_args: list[str] | None = None,
    ) -> tuple[run_demo.DemoReport | None, run_demo.InfoReport | None]:
        captured["name"] = path.name
        captured["verbose"] = verbose
        captured["llm_delay"] = llm_delay
        captured["demo_args"] = demo_args
        return _demo_report(baseline_pass=True, compiler_pass=True), None

    monkeypatch.setattr(run_demo, "_run", fake_run)
    monkeypatch.setattr("sys.argv", ["run_demo", "3"])

    run_demo.main()

    assert captured == {
        "name": "03_llm_premise_guardrail.py",
        "verbose": False,
        "llm_delay": 0,
        "demo_args": None,
    }


def test_runner_prints_per_demo_compiler_regression_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(
        path: Path, *, verbose: bool, llm_delay: float
    ) -> tuple[run_demo.DemoReport | None, run_demo.InfoReport | None]:
        assert not verbose
        assert llm_delay == 0
        print("01_fake — regression fixture")
        print("baseline: PASS")
        print("compiler: FAIL")
        print("expected: expected behavior")
        print("actual: actual behavior")
        print("result: corrected value determined the final plan")
        return _demo_report(baseline_pass=True, compiler_pass=False), None

    monkeypatch.setattr(run_demo, "DEMO_FILES", {"1": "fake_01.py"})
    monkeypatch.setattr(run_demo, "SCORED_DEMOS", {"1"})
    monkeypatch.setattr(run_demo, "_run", fake_run)
    monkeypatch.setattr("sys.argv", ["run_demo", "1"])

    with pytest.raises(SystemExit) as exc_info:
        run_demo.main()
    output = capsys.readouterr().out

    assert exc_info.value.code == 1
    assert "result:" in output
    assert "⚠️ MEDIATED REGRESSION" in output
    assert "baseline succeeded but compiler-mediated version failed" in output
    result_index = output.index("result:")
    warning_index = output.index("⚠️ MEDIATED REGRESSION")
    detail_index = output.index("baseline succeeded but compiler-mediated version failed")
    assert result_index < warning_index < detail_index


def test_runner_prints_summary_regression_banner_in_all_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(
        path: Path, *, verbose: bool, llm_delay: float
    ) -> tuple[run_demo.DemoReport | None, run_demo.InfoReport | None]:
        assert not verbose
        assert llm_delay == 0
        if path.name == "fake_01.py":
            print("01_fake — regression fixture")
            print("baseline: PASS")
            print("compiler: FAIL")
            print("expected: expected behavior")
            print("actual: actual behavior")
            print("result: regression observed")
            return _demo_report(baseline_pass=True, compiler_pass=False), None
        print("06_context_compaction — superseded directives eliminated")
        print("context: 137 → 37 chars")
        print("prompt: 247 → 160 chars")
        print("reduction: context 73%; prompt 35%")
        print("result: compiled authoritative state replaced superseded transcript directives")
        return None, _info_report()

    monkeypatch.setattr(run_demo, "DEMO_FILES", {"1": "fake_01.py", "6": "fake_06.py"})
    monkeypatch.setattr(run_demo, "SCORED_DEMOS", {"1"})
    monkeypatch.setattr(run_demo, "_run", fake_run)
    monkeypatch.setattr("sys.argv", ["run_demo", "all"])

    with pytest.raises(SystemExit) as exc_info:
        run_demo.main()
    output = capsys.readouterr().out

    assert exc_info.value.code == 1
    assert "Baseline results: 1 passed, 0 failed" in output
    assert "Compiler results: 0 passed, 1 failed" in output
    assert "Compiler+compact results: 0 passed, 1 failed" in output
    assert "*** 1 MEDIATED REGRESSION DETECTED ***" in output


def test_runner_prints_plural_summary_regression_banner_in_all_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(
        path: Path, *, verbose: bool, llm_delay: float
    ) -> tuple[run_demo.DemoReport | None, run_demo.InfoReport | None]:
        assert not verbose
        assert llm_delay == 0
        if path.name in {"fake_01.py", "fake_02.py"}:
            print(f"{path.stem} — regression fixture")
            print("baseline: PASS")
            print("compiler: FAIL")
            print("expected: expected behavior")
            print("actual: actual behavior")
            print("result: regression observed")
            return _demo_report(baseline_pass=True, compiler_pass=False), None
        print("06_context_compaction — superseded directives eliminated")
        print("context: 137 → 37 chars")
        print("prompt: 247 → 160 chars")
        print("reduction: context 73%; prompt 35%")
        print("result: compiled authoritative state replaced superseded transcript directives")
        return None, _info_report()

    monkeypatch.setattr(
        run_demo,
        "DEMO_FILES",
        {"1": "fake_01.py", "2": "fake_02.py", "6": "fake_06.py"},
    )
    monkeypatch.setattr(run_demo, "SCORED_DEMOS", {"1", "2"})
    monkeypatch.setattr(run_demo, "_run", fake_run)
    monkeypatch.setattr("sys.argv", ["run_demo", "all"])

    with pytest.raises(SystemExit) as exc_info:
        run_demo.main()
    output = capsys.readouterr().out

    assert exc_info.value.code == 1
    assert "Baseline results: 2 passed, 0 failed" in output
    assert "Compiler results: 0 passed, 2 failed" in output
    assert "Compiler+compact results: 0 passed, 2 failed" in output
    assert "*** 2 MEDIATED REGRESSIONS DETECTED ***" in output


def test_informational_demo_is_non_scored_in_all_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(
        path: Path, *, verbose: bool, llm_delay: float
    ) -> tuple[run_demo.DemoReport | None, run_demo.InfoReport | None]:
        assert not verbose
        assert llm_delay == 0
        if path.name == "fake_01.py":
            print("01_fake — pass fixture")
            print("baseline: PASS")
            print("compiler: PASS")
            print("expected: expected behavior")
            print("actual: actual behavior")
            print("result: success")
            return _demo_report(baseline_pass=True, compiler_pass=True), None
        print("06_context_compaction — superseded directives eliminated")
        print("context: 137 → 37 chars")
        print("prompt: 247 → 160 chars")
        print("reduction: context 73%; prompt 35%")
        print("result: compiled authoritative state replaced superseded transcript directives")
        return None, _info_report()

    monkeypatch.setattr(run_demo, "DEMO_FILES", {"1": "fake_01.py", "6": "fake_06.py"})
    monkeypatch.setattr(run_demo, "SCORED_DEMOS", {"1"})
    monkeypatch.setattr(run_demo, "_run", fake_run)
    monkeypatch.setattr("sys.argv", ["run_demo", "all"])

    run_demo.main()
    output = capsys.readouterr().out

    assert "Baseline results: 1 passed, 0 failed" in output
    assert "Compiler results: 1 passed, 0 failed" in output
    assert "Compiler+compact results: 1 passed, 0 failed" in output
    assert (
        "06_context_compaction — context 137 → 37 chars (73% reduction); "
        "prompt 247 → 160 chars (35% reduction)"
    ) in output
    assert "*** 1 MEDIATED REGRESSION DETECTED ***" not in output


def test_runner_prints_friendly_demo_llm_error_in_single_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(
        path: Path, *, verbose: bool, llm_delay: float
    ) -> tuple[run_demo.DemoReport | None, run_demo.InfoReport | None]:
        assert llm_delay == 0
        raise DemoLLMError(
            "Model 'bad-model' was not found at the configured endpoint. "
            "Check MODEL or OPENAI_BASE_URL."
        )

    monkeypatch.setattr(run_demo, "DEMO_FILES", {"1": "fake_01.py"})
    monkeypatch.setattr(run_demo, "SCORED_DEMOS", {"1"})
    monkeypatch.setattr(run_demo, "_run", fake_run)
    monkeypatch.setattr("sys.argv", ["run_demo", "1"])

    with pytest.raises(SystemExit) as exc_info:
        run_demo.main()
    output = capsys.readouterr().out

    assert exc_info.value.code == 2
    assert (
        "Model 'bad-model' was not found at the configured endpoint. "
        "Check MODEL or OPENAI_BASE_URL."
    ) in output


def test_all_mode_scored_none_result_counts_as_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(
        path: Path, *, verbose: bool, llm_delay: float
    ) -> tuple[run_demo.DemoReport | None, run_demo.InfoReport | None]:
        assert not verbose
        assert llm_delay == 0
        if path.name == "fake_01.py":
            return None, None
        print("06_context_compaction — superseded directives eliminated")
        print("context: 137 → 37 chars")
        print("prompt: 247 → 160 chars")
        print("reduction: context 73%; prompt 35%")
        print("result: compiled authoritative state replaced superseded transcript directives")
        return None, _info_report()

    monkeypatch.setattr(run_demo, "DEMO_FILES", {"1": "fake_01.py", "6": "fake_06.py"})
    monkeypatch.setattr(run_demo, "SCORED_DEMOS", {"1"})
    monkeypatch.setattr(run_demo, "_run", fake_run)
    monkeypatch.setattr("sys.argv", ["run_demo", "all"])

    run_demo.main()
    output = capsys.readouterr().out

    assert "Baseline results: 0 passed, 1 failed" in output
    assert "Compiler results: 0 passed, 1 failed" in output
    assert "Compiler+compact results: 0 passed, 1 failed" in output


def test_all_mode_counts_baseline_fail_and_compiler_pass(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(
        path: Path, *, verbose: bool, llm_delay: float
    ) -> tuple[run_demo.DemoReport | None, run_demo.InfoReport | None]:
        assert not verbose
        assert llm_delay == 0
        if path.name == "fake_01.py":
            print("01_fake — mixed fixture")
            print("baseline: FAIL")
            print("compiler: PASS")
            print("expected: expected behavior")
            print("actual: actual behavior")
            print("result: mixed outcome")
            return _demo_report(baseline_pass=False, compiler_pass=True), None
        print("06_context_compaction — superseded directives eliminated")
        print("context: 137 → 37 chars")
        print("prompt: 247 → 160 chars")
        print("reduction: context 73%; prompt 35%")
        print("result: compiled authoritative state replaced superseded transcript directives")
        return None, _info_report()

    monkeypatch.setattr(run_demo, "DEMO_FILES", {"1": "fake_01.py", "6": "fake_06.py"})
    monkeypatch.setattr(run_demo, "SCORED_DEMOS", {"1"})
    monkeypatch.setattr(run_demo, "_run", fake_run)
    monkeypatch.setattr("sys.argv", ["run_demo", "all"])

    run_demo.main()
    output = capsys.readouterr().out

    assert "Baseline results: 0 passed, 1 failed" in output
    assert "Compiler results: 1 passed, 0 failed" in output
    assert "Compiler+compact results: 1 passed, 0 failed" in output


def test_single_scored_demo_without_mediated_regression_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        path: Path, *, verbose: bool, llm_delay: float
    ) -> tuple[run_demo.DemoReport | None, run_demo.InfoReport | None]:
        assert path.name == "fake_01.py"
        assert not verbose
        assert llm_delay == 0
        return _demo_report(baseline_pass=True, compiler_pass=True), None

    monkeypatch.setattr(run_demo, "DEMO_FILES", {"1": "fake_01.py"})
    monkeypatch.setattr(run_demo, "SCORED_DEMOS", {"1"})
    monkeypatch.setattr(run_demo, "_run", fake_run)
    monkeypatch.setattr("sys.argv", ["run_demo", "1"])

    run_demo.main()


def test_compaction_demo_reports_sane_metrics() -> None:
    consume_last_info_report()

    demo_path = Path(__file__).resolve().parents[1] / "demos" / "06_llm_context_compaction.py"
    runpy.run_path(str(demo_path), run_name="__main__")

    report = consume_last_info_report()
    assert report is not None
    assert report["name"].startswith("06_context_compaction")
    assert report["baseline_context_length"] > report["compiled_context_length"]
    assert report["baseline_prompt_length"] > report["compiled_prompt_length"]
    assert report["context_reduction_percent"] > 0
    assert report["prompt_reduction_percent"] > 0
    assert report["compacted_context_length"] <= report["baseline_context_length"]
    assert report["compacted_prompt_length"] <= report["baseline_prompt_length"]


def test_runner_passes_llm_delay_from_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, float] = {}

    def fake_run(
        path: Path, *, verbose: bool, llm_delay: float
    ) -> tuple[run_demo.DemoReport | None, run_demo.InfoReport | None]:
        assert path.name == "fake_06.py"
        assert not verbose
        captured["llm_delay"] = llm_delay
        return None, None

    monkeypatch.setattr(run_demo, "DEMO_FILES", {"6": "fake_06.py"})
    monkeypatch.setattr(run_demo, "SCORED_DEMOS", {"1", "2", "3", "4", "5"})
    monkeypatch.setattr(run_demo, "_run", fake_run)
    monkeypatch.setattr("sys.argv", ["run_demo", "6", "--llm-delay", "1.25"])

    run_demo.main()

    assert captured["llm_delay"] == 1.25


def test_runner_forwards_demo_specific_args_after_separator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(
        path: Path,
        *,
        verbose: bool,
        llm_delay: float,
        demo_args: list[str] | None = None,
    ) -> tuple[run_demo.DemoReport | None, run_demo.InfoReport | None]:
        assert path.name == "fake_05.py"
        assert not verbose
        captured["llm_delay"] = llm_delay
        captured["demo_args"] = demo_args
        return _demo_report(baseline_pass=True, compiler_pass=True), None

    monkeypatch.setattr(run_demo, "DEMO_FILES", {"5": "fake_05.py"})
    monkeypatch.setattr(run_demo, "SCORED_DEMOS", {"5"})
    monkeypatch.setattr(run_demo, "_run", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        ["run_demo", "5", "--llm-delay", "1.25", "--", "--turns", "120"],
    )

    run_demo.main()

    assert captured["llm_delay"] == 1.25
    assert captured["demo_args"] == ["--turns", "120"]
