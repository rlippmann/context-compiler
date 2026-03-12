"""Run one or all LLM demos."""

import argparse
import os
import runpy
import sys
from pathlib import Path

from demos.common import (
    VERBOSE_ENV_VAR,
    DemoReport,
    InfoReport,
    consume_last_info_report,
    consume_last_report,
)
from demos.llm_client import DemoLLMError, MissingDemoConfigError

DEMO_FILES: dict[str, str] = {
    "1": "01_llm_constraint_drift.py",
    "2": "02_llm_correction_replacement.py",
    "3": "03_llm_ambiguity_block.py",
    "4": "04_llm_tool_governance.py",
    "5": "05_llm_prompt_drift.py",
    "6": "06_context_compaction.py",
}

SCORED_DEMOS = {"1", "2", "3", "4", "5"}


def _verbose_demo_label(path: Path) -> str:
    return path.stem.replace("_llm", "")


def _is_compiler_regression(result: DemoReport) -> bool:
    return bool(result["baseline_pass"]) and not bool(result["compiler_pass"])


def _print_compiler_regression_warning() -> None:
    print()
    print("⚠️ MEDIATED REGRESSION")
    print("baseline succeeded but compiler-mediated version failed")


def _run(path: Path, *, verbose: bool) -> tuple[DemoReport | None, InfoReport | None]:
    if verbose:
        print(f"===== Running {_verbose_demo_label(path)} =====")
    old_value = os.getenv(VERBOSE_ENV_VAR)
    os.environ[VERBOSE_ENV_VAR] = "1" if verbose else "0"
    try:
        runpy.run_path(str(path), run_name="__main__")
        return consume_last_report(), consume_last_info_report()
    finally:
        if old_value is None:
            os.environ.pop(VERBOSE_ENV_VAR, None)
        else:
            os.environ[VERBOSE_ENV_VAR] = old_value


def _print_config_error(exc: MissingDemoConfigError) -> None:
    mode = "OpenAI-compatible endpoint" if exc.base_url else "OpenAI API"
    print("Unable to run LLM demos: missing model configuration.")
    print(f"Assumed mode: {mode}")
    print(f"Missing variables: {', '.join(exc.missing)}")
    print("Example setup:")
    if exc.base_url:
        print("  export OPENAI_BASE_URL=http://localhost:11434/v1")
        print("  export OPENAI_API_KEY=ollama")
        print("  export MODEL=llama3.1:8b")
    else:
        print("  export OPENAI_API_KEY=your_key_here")
        print("  export MODEL=gpt-4.1-mini")


def main() -> None:
    root = Path(__file__).resolve().parent
    project_root = root.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    parser = argparse.ArgumentParser(description="Run context-compiler LLM demos.")
    parser.add_argument(
        "demo",
        nargs="?",
        default="all",
        choices=["all", *DEMO_FILES.keys()],
        help="Demo number (1-6) or all",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed prompts, compiler decisions, and model output excerpts.",
    )
    args = parser.parse_args()

    if args.demo == "all":
        baseline_pass_count = 0
        baseline_fail_count = 0
        compiler_pass_count = 0
        compiler_fail_count = 0
        compiler_regressions = 0
        informational_reports: list[InfoReport] = []
        for index, key in enumerate(sorted(DEMO_FILES.keys())):
            if index > 0 and not args.verbose:
                print()
            try:
                result, info_report = _run(root / DEMO_FILES[key], verbose=args.verbose)
            except MissingDemoConfigError as exc:
                _print_config_error(exc)
                raise SystemExit(2) from exc
            except DemoLLMError as exc:
                print(str(exc))
                raise SystemExit(2) from exc

            if info_report is not None:
                informational_reports.append(info_report)

            if key not in SCORED_DEMOS:
                continue

            if result is None:
                baseline_fail_count += 1
                compiler_fail_count += 1
                continue

            if bool(result["baseline_pass"]):
                baseline_pass_count += 1
            else:
                baseline_fail_count += 1

            if bool(result["compiler_pass"]):
                compiler_pass_count += 1
            else:
                compiler_fail_count += 1

            if _is_compiler_regression(result):
                compiler_regressions += 1
                _print_compiler_regression_warning()
        print()
        print("Summary:")
        print()
        print("Evaluative demos:")
        print(f"Baseline results: {baseline_pass_count} passed, {baseline_fail_count} failed")
        print(f"Compiler results: {compiler_pass_count} passed, {compiler_fail_count} failed")
        if compiler_regressions > 0:
            print()
            if compiler_regressions == 1:
                print("*** 1 MEDIATED REGRESSION DETECTED ***")
            else:
                print(f"*** {compiler_regressions} MEDIATED REGRESSIONS DETECTED ***")
        if informational_reports:
            print()
            print("Informational demo:")
            for report in informational_reports:
                demo_id = report["name"].split(" — ", maxsplit=1)[0]
                print(
                    f"{demo_id} — context {report['baseline_context_length']} "
                    f"→ {report['compiled_context_length']} chars "
                    f"({report['context_reduction_percent']}% reduction); "
                    f"prompt {report['baseline_prompt_length']} "
                    f"→ {report['compiled_prompt_length']} chars "
                    f"({report['prompt_reduction_percent']}% reduction)"
                )
        return

    try:
        result, _ = _run(root / DEMO_FILES[args.demo], verbose=args.verbose)
    except MissingDemoConfigError as exc:
        _print_config_error(exc)
        raise SystemExit(2) from exc
    except DemoLLMError as exc:
        print(str(exc))
        raise SystemExit(2) from exc
    if args.demo in SCORED_DEMOS and result is not None and _is_compiler_regression(result):
        _print_compiler_regression_warning()


if __name__ == "__main__":
    main()
