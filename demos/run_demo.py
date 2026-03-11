"""Run one or all LLM demos."""

import argparse
import runpy
import sys
from pathlib import Path

DEMO_FILES: dict[str, str] = {
    "1": "01_llm_constraint_drift.py",
    "2": "02_llm_correction_replacement.py",
    "3": "03_llm_ambiguity_block.py",
    "4": "04_llm_tool_governance.py",
    "5": "05_llm_prompt_drift.py",
}


def _run(path: Path) -> None:
    print(f"===== Running {path.name} =====")
    runpy.run_path(str(path), run_name="__main__")


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
    args = parser.parse_args()

    if args.demo == "all":
        for key in sorted(DEMO_FILES.keys()):
            _run(root / DEMO_FILES[key])
        return

    _run(root / DEMO_FILES[args.demo])


if __name__ == "__main__":
    main()
