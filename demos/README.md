# LLM Demos

These scripts compare baseline prompting vs compiler-mediated prompting using the
Context Compiler decision/state API.
They are illustrative manual demos, not benchmarks or CI tests.
They demonstrate common LLM failure modes and how authoritative compiled state
can improve reliability.

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

Run a single demo:

```bash
uv run python -m demos.run_demo 1
```

Run all demos:

```bash
uv run python -m demos.run_demo all
```

Run all demos with detailed traces:

```bash
uv run python -m demos.run_demo all --verbose
```

## Output modes

- `Default (concise)`:
  - scenario name + description
  - for evaluative demos (`01`–`05`):
    - `baseline: PASS|FAIL`
    - `compiler: PASS|FAIL`
  - expected behavior
  - actual outcome
  - `result: ...` (short deterministic description)
  - for `06_context_compaction`:
    - `context: <baseline> → <compiled> chars`
    - `prompt: <baseline> → <compiled> chars`
    - `reduction: context <pct>%; prompt <pct>%`
    - `result: ...`
  - when running `all`:
    - blank line between demos
    - final summary with evaluative totals
    - informational summary line for `06_context_compaction` (non-scored)
- `Verbose (--verbose)`:
  - user inputs
  - compiler decisions and compiled state
  - prompts/messages sent to the LLM
  - output excerpts
  - host checks and final verdict
  - for `06_context_compaction`, also:
    - raw transcript context
    - compiled context
    - baseline and compiled prompts
    - context and prompt size comparisons
