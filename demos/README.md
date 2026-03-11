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

- `MODEL` (required): model name
- `OPENAI_API_KEY` (required for OpenAI API)
- `OPENAI_BASE_URL` (optional; use for OpenAI-compatible local servers)

Ollama example:

```bash
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_API_KEY=ollama
export MODEL=llama3.1
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

- default (concise): each demo prints only four lines
  - scenario name + short description
  - expected behavior
  - actual outcome (plain English)
  - `PASS` or `FAIL`
- `--verbose`: prints detailed traces
  - user inputs
  - compiler decisions and state
  - prompts/messages sent to the LLM
  - output excerpts
  - host checks and final verdict
