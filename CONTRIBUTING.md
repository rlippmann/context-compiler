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
