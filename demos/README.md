# LLM Demos

These scripts compare baseline prompting vs compiler-mediated prompting using the
Context Compiler decision/state API.
They are illustrative manual demos, not benchmarks or CI tests.

## Requirements

Install demo dependencies:

```bash
pip install -e .[demos]
```

Environment variables:

- `MODEL` (optional; default: `gpt-4.1-mini`)
- `OPENAI_API_KEY` (required)
- `OPENAI_BASE_URL` (optional; use for OpenAI-compatible local servers)

Ollama example:

```bash
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_API_KEY=ollama
export MODEL=llama3.1:8b
```

OpenAI example:

```bash
export OPENAI_API_KEY=your_key_here
export MODEL=gpt-4.1-mini
```

## Run

Run one demo:

```bash
uv run python -m demos.run_demo 1
```

Run all demos:

```bash
uv run python -m demos.run_demo all
```

Verbose mode:

```bash
uv run python -m demos.run_demo all --verbose
```

Output modes:

- default (concise): each demo prints the following:
  - scenario name + short description
  - `baseline: PASS|FAIL`
  - `compiler: PASS|FAIL`
  - expected behavior
  - actual outcome (plain English)
  - `result: ...` (short deterministic description)
  - a blank line between demos when running `all`
  - final summary:
    - `Baseline results: X passed, Y failed`
    - `Compiler results: X passed, Y failed`
- `--verbose`: prints detailed traces
  - user inputs
  - compiler decisions and state
  - prompts/messages sent to the LLM
  - output excerpts
  - host checks and final verdict
