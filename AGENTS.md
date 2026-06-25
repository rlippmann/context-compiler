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

## Test coverage expectations
Before opening a PR, consider:

* Does this change affect any user-facing behavior?
* If so, is that behavior covered by tests?

User-facing behavior includes:

* engine decision outcomes (`kind`, `prompt_to_user`)
* checkpoint export/import and continuation behavior
* clarify/confirmation flows (`yes` / `no`)
* controller behavior (`step`, `preview`, `state_diff`)
* REPL / CLI behavior
* authoritative state semantics
* conformance fixture behavior

If a user-facing behavior is changed or introduced, add or update tests to cover it.

Do not rely solely on coverage metrics.

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
- Always use the repository PR template when creating or updating PR descriptions.
- PR titles must use the same format as commits: `<type>: <summary>`.
- PR descriptions should include:
  - what changed
  - why the change was needed
- Do not include a dedicated "Validation" section in PR text.
- Keep PR scope aligned to the requested task; if scope grows, ask for guidance before expanding.

## Issue guidance
- Always use the repository issue templates when creating or updating issues.
- Use `bug_report` for defects and regressions.
- Use `feature_request` for new capabilities or enhancements.

## CI
Do not modify GitHub CI workflows unless explicitly asked.

## Documentation
Specification documents are authoritative.

Do not change specification documents unless explicitly instructed.

If implementation behavior does not match the specification, report the mismatch instead of modifying the specification.

Documentation is not commentary.

README examples, demos, migration guides, CLI usage
documentation, and explicitly requested documentation changes are part of the
project contract.

Treat documentation requirements in a task as acceptance criteria.

Do not treat documentation as illustrative unless explicitly stated.
Do not silently change documented behavior because implementation is easier.
Do not update documentation merely to match unintended behavior.
Do not weaken or remove user-facing tests to accommodate implementation.

Documentation examples explicitly referenced by a task are part of the
expected deliverable.

If implementation, documentation, examples, tests, fixtures, and
specifications disagree:

1. Specifications and fixtures are authoritative.
2. Report the mismatch.
3. Request review before changing documented behavior.
4. Do not resolve disagreements by silently changing docs.

## Documentation style

For README, demo, and package-listing docs, explain user-visible behavior before architecture.

Prefer plain, concrete wording when accurate. Examples:
- "rules and corrections that stick"
- "saved compiler state"
- "stored premise and policy rules"
- "fixed, repeatable"
- "explicit instructions stay consistent across turns"

Avoid describing features only in architectural terms when a behavior-first explanation is possible.

Prefer direct subjects and strong verbs.
Avoid noun stacks and passive phrasing when a simpler active sentence is clearer.
Use simpler wording unless technical precision requires formal terminology.

Specification and contract documents are different:
- preserve precise terminology
- preserve unambiguous behavioral guarantees
- do not weaken formal semantics for readability

Do not rewrite captured outputs, fixture-sensitive examples, or eval evidence unless explicitly asked.

## Tooling
Use the project's existing tooling:

- Run commands via `uv run` when appropriate.
- Development dependencies are installed with `uv sync --group dev`.

## Structured Regression Fixtures
- Deterministic engine behavior changes that affect `tests/fixtures/engine-regression/structured/` outputs must update the corresponding fixtures.
- Fixture updates must be intentional; do not regenerate fixtures casually or as a side effect of normal test runs.
- If a PR changes structured fixtures, the PR description must explain:
  - what behavioral contract changed
  - why it changed
