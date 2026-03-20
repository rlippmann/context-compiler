# AGENTS.md

Guidelines for AI agents working in this repository.

## Branch rules
- Never commit directly to `main`.
- Never push directly to `main`.
- Never check out or modify `main`.
- Always work on a feature branch.
- If the current branch is `main`, stop and ask the user to create a branch.

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

## Git safety
- Do not perform history-rewriting operations unless explicitly instructed.
- This includes `git rebase`, `git reset`, `git push --force`, and `git commit --amend`.
- Do not push directly to `main`.
- Do not check out or modify `main`.
- If the current branch is `main`, stop and ask the user to create a feature branch.

## Commit messages
- Commit messages must use this format: `<type>: <summary>`.
- The `<type>` token must be lowercase letters only.
- The `<summary>` must be short and written in imperative mood.
- Allowed `<type>` values: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`.
- If a proposed commit message does not match this format or type list, stop and ask for a corrected message before committing.

## PR guidance
- Never open or merge a PR targeting `main` from `main`; always use a feature branch.
- PR titles must use the same format as commits: `<type>: <summary>`.
- PR descriptions should include:
  - what changed
  - why the change was needed
- A dedicated "Validation" section in PR text is optional and not required.
- Keep PR scope aligned to the requested task; if scope grows, ask for guidance before expanding.

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
