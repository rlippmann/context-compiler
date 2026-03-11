"""Run one or all LLM demos."""

import argparse
import os
import runpy
import sys
from pathlib import Path

from demos.common import VERBOSE_ENV_VAR, consume_last_report_passed

DEMO_FILES: dict[str, str] = {
    "1": "01_llm_constraint_drift.py",
    "2": "02_llm_correction_replacement.py",
    "3": "03_llm_ambiguity_block.py",
    "4": "04_llm_tool_governance.py",
    "5": "05_llm_prompt_drift.py",
}


def _run(path: Path, *, verbose: bool) -> bool | None:
    if verbose:
        print(f"===== Running {path.name} =====")
    old_value = os.getenv(VERBOSE_ENV_VAR)
    os.environ[VERBOSE_ENV_VAR] = "1" if verbose else "0"
    try:
        runpy.run_path(str(path), run_name="__main__")
        return consume_last_report_passed()
    finally:
        if old_value is None:
            os.environ.pop(VERBOSE_ENV_VAR, None)
        else:
            os.environ[VERBOSE_ENV_VAR] = old_value


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
        help="Demo number (1-5) or all",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed prompts, compiler decisions, and model output excerpts.",
    )
    args = parser.parse_args()

    if args.demo == "all":
        passed = 0
        failed = 0
        for key in sorted(DEMO_FILES.keys()):
            result = _run(root / DEMO_FILES[key], verbose=args.verbose)
            if result is True:
                passed += 1
            else:
                failed += 1
        print("=" * 60)
        print(f"Context Compiler demos complete: {passed} passed, {failed} failed")
        return

    _run(root / DEMO_FILES[args.demo], verbose=args.verbose)


if __name__ == "__main__":
    main()
