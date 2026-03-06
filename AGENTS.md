# AGENTS.md

Guidelines for AI agents working in this repository.

## Branch rules
- Never commit directly to `main`.
- Always create or use a feature branch for changes.
- If the current branch is `main`, stop and ask the user to create a branch before proceeding.

## Development workflow
Before committing:
1. Run `pre-commit run --all-files`
2. Run `pytest`

Do not bypass pre-commit hooks.

## Scope of changes
- Only modify files necessary for the requested task.
- Do not refactor unrelated code.
- Do not change project structure unless explicitly asked.
- Make the minimal change required to solve the requested task.
- If the task expands beyond the original request, stop and ask the user for guidance.

## Dependencies
If tests fail due to missing dependencies, install them rather than skipping tests.

## Python version
This project targets modern Python (3.11+).

Do not add compatibility code for older Python versions.

Avoid constructs that were only required for older Python versions, including:
- `from __future__ import annotations`
- `typing_extensions` replacements for stdlib features
- version guards like `if sys.version_info < ...`

Prefer modern typing syntax:
- `list[str]` instead of `List[str]`
- `dict[str, int]` instead of `Dict[str, int]`
- `str | None` instead of `Optional[str]`

## CI
Do not modify GitHub CI workflows unless explicitly asked.

## Documentation
Specification documents are authoritative.

Do not change specification documents unless explicitly instructed.

If implementation behavior does not match the specification, report the mismatch instead of modifying the specification.

## Tooling
Use the project's existing tooling:

- Run commands via `uv run` when appropriate.
- Development dependencies are installed with `uv sync --group dev`.
