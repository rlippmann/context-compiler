# Contributing

Thanks for your interest in improving this project. Contributions are welcome.

## Workflow

Contributions are typically submitted via fork and pull request:

- fork the repository
- create a feature branch
- run tests and pre-commit checks
- open a pull request

## Development Setup

```bash
uv sync --group dev
```

## Running Tests

```bash
uv run pytest
```

## Code Quality

```bash
pre-commit run --all-files
```

## Scope of Changes

- keep pull requests focused
- include tests if behavior changes
- open an issue first for large design changes

## Documentation Style

For README, demo, integration, and package-listing docs, explain user-visible behavior before architecture.

Prefer plain, concrete wording when accurate. For example:
- "rules and corrections that stick"
- "saved compiler state"
- "stored premise and policy rules"
- "fixed, repeatable"
- "explicit instructions stay consistent across turns"

Avoid describing features only in architectural terms when a behavior-first explanation is possible.

Specification and contract documents are different: preserve precise terminology and unambiguous behavioral guarantees. Do not simplify formal docs in ways that weaken guarantees or change meaning.

Do not rewrite captured outputs, fixture-sensitive examples, or eval evidence unless explicitly asked.
