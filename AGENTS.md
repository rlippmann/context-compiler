# AGENTS.md

Guidelines for AI agents working in this repository.

## Branch rules
- Never commit directly to `main`.
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

## CI
Do not modify GitHub CI workflows unless explicitly asked.

## Documentation
If implementation behavior changes, update the specification documents to match.
