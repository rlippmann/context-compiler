import runpy
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from demos import run_demo  # noqa: E402
from demos.common import consume_last_info_report  # noqa: E402


def _demo_report(*, baseline_pass: bool, compiler_pass: bool) -> run_demo.DemoReport:
    return {
        "name": "01_fake — regression fixture",
        "expected": "expected behavior",
        "actual": "actual behavior",
        "baseline_pass": baseline_pass,
        "compiler_pass": compiler_pass,
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


def test_runner_prints_per_demo_compiler_regression_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(
        path: Path, *, verbose: bool
    ) -> tuple[run_demo.DemoReport | None, run_demo.InfoReport | None]:
        assert not verbose
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

    run_demo.main()
    output = capsys.readouterr().out

    assert "result:" in output
    assert "⚠️ COMPILER REGRESSION" in output
    assert "baseline succeeded but compiler-mediated version failed" in output
    result_index = output.index("result:")
    warning_index = output.index("⚠️ COMPILER REGRESSION")
    detail_index = output.index("baseline succeeded but compiler-mediated version failed")
    assert result_index < warning_index < detail_index


def test_runner_prints_summary_regression_banner_in_all_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(
        path: Path, *, verbose: bool
    ) -> tuple[run_demo.DemoReport | None, run_demo.InfoReport | None]:
        assert not verbose
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

    run_demo.main()
    output = capsys.readouterr().out

    assert "Baseline results: 1 passed, 0 failed" in output
    assert "Compiler results: 0 passed, 1 failed" in output
    assert "*** 1 COMPILER REGRESSION DETECTED ***" in output


def test_runner_prints_plural_summary_regression_banner_in_all_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(
        path: Path, *, verbose: bool
    ) -> tuple[run_demo.DemoReport | None, run_demo.InfoReport | None]:
        assert not verbose
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

    run_demo.main()
    output = capsys.readouterr().out

    assert "Baseline results: 2 passed, 0 failed" in output
    assert "Compiler results: 0 passed, 2 failed" in output
    assert "*** 2 COMPILER REGRESSIONS DETECTED ***" in output


def test_informational_demo_is_non_scored_in_all_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(
        path: Path, *, verbose: bool
    ) -> tuple[run_demo.DemoReport | None, run_demo.InfoReport | None]:
        assert not verbose
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
    assert (
        "06_context_compaction — context 137 → 37 chars (73% reduction); "
        "prompt 247 → 160 chars (35% reduction)"
    ) in output
    assert "*** 1 COMPILER REGRESSION DETECTED ***" not in output


def test_all_mode_scored_none_result_counts_as_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(
        path: Path, *, verbose: bool
    ) -> tuple[run_demo.DemoReport | None, run_demo.InfoReport | None]:
        assert not verbose
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


def test_all_mode_counts_baseline_fail_and_compiler_pass(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(
        path: Path, *, verbose: bool
    ) -> tuple[run_demo.DemoReport | None, run_demo.InfoReport | None]:
        assert not verbose
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


def test_compaction_demo_reports_sane_metrics() -> None:
    consume_last_info_report()

    demo_path = Path(__file__).resolve().parents[1] / "demos" / "06_context_compaction.py"
    runpy.run_path(str(demo_path), run_name="__main__")

    report = consume_last_info_report()
    assert report is not None
    assert report["name"].startswith("06_context_compaction")
    assert report["baseline_context_length"] > report["compiled_context_length"]
    assert report["baseline_prompt_length"] > report["compiled_prompt_length"]
    assert report["context_reduction_percent"] > 0
    assert report["prompt_reduction_percent"] > 0
