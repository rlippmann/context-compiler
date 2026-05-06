# LLM Demos

These scripts show common ways LLM conversations can go wrong.

They compare normal prompting with an approach where the application tracks
important instructions explicitly instead of relying only on the conversation
history. The scripts are designed to produce consistent results so the
behavior is easy to see.

Scored demos now compare three paths:
- baseline
- compiler-mediated (full transcript + injected state)
- compiler+compact (compacted transcript + injected state)

## Demo overview

| Demo | Behavior | Concept | Most visible with |
| :--: | --- | :--: | --- |
| [01](./01_llm_contradiction_clarify.py) | Contradiction blocking | clarification gate | small instruct models |
| [02](./02_llm_constraint_guardrail.py) | Constraint drift | persistent policy enforcement | small or quantized models |
| [03](./03_llm_premise_guardrail.py) | Premise update drift | deterministic premise updates | models that summarize conversation |
| [04](./04_llm_tool_denylist_guardrail.py) | Tool governance | host-side denylist | general assistant models |
| [05](./05_llm_prompt_drift_vs_state.py) | Prompt drift | long transcript failure | weaker long-context models ([see Demo 5 note](#demo-5-stress-ladder-turns)) |
| [06](./06_llm_context_compaction.py) | Context compaction | compiled state replacing transcript | small or local models |
| [07](./07_llm_prompt_vs_state.py) | Prompt engineering comparison | prompting vs compiled state | any model with long transcript sensitivity |

Stronger frontier models may show these behaviors less often, but the same
patterns still appear in real applications.

## Requirements

Install demo dependencies:

```bash
pip install "context-compiler[demos]"
```

Environment variables (strict provider mode contract):

- `PROVIDER` (optional): `openai` (default), `ollama`, `openai_compatible`
- `MODEL` (optional)
- `OPENAI_API_KEY` (required in normal `openai` mode)
- `OPENAI_BASE_URL` (explicit endpoint override; required for explicit `openai_compatible`)
Note: Demos prefer deterministic decoding (`temperature=0`) for reproducible PASS/FAIL behavior.
If a model rejects that parameter (for example, some `gpt-5` paths), the demo client retries once without it.

Default (openai):

```bash
export OPENAI_API_KEY=your_key_here
export MODEL=gpt-4.1-mini
```

Ollama mode:

```bash
export PROVIDER=ollama
export MODEL=ollama/llama3.1:8b
```

Ollama mode uses a direct base URL of `http://localhost:11434`.

Explicit openai_compatible mode:

```bash
export PROVIDER=openai_compatible
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_API_KEY=ollama
export MODEL=openai/llama3.1:8b
```

## Quick run

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

## Results

The canonical cross-model results matrix is maintained in [docs/demos-results.md](../docs/demos-results.md).

Notes:
- There are **6 scored demos** (`01`–`05`, `07`). `06_context_compaction` is informational and excluded from PASS/FAIL totals.
- Anthropic runs in this repo are executed through the `openai_compatible` provider path.
- `PASS` means the demo-specific oracle/checker for that path succeeded; `FAIL` means it did not.

### Demo 05 example (real run excerpt)

Demo 05 measures prompt drift versus authoritative compiled state on a longer transcript.
Representative output excerpt from a local run (`ollama/qwen2.5:14b-instruct`):

```text
05_prompt_drift — preserve premise across long transcript
baseline: PASS
compiler: PASS
compiler+compact: PASS
expected: compiler-mediated should preserve the authoritative premise and keep the plan consistent
actual: all three paths preserved premise-consistent plan
result: premise consistency preserved
```

This is one representative scored demo behind the aggregate results matrix above.

## Provider throttling

The demos make multiple LLM requests and may trigger rate limits on very
low-quota hosted providers (especially free tiers).

If you encounter throttling, you can slow requests using:

```bash
uv run python -m demos.run_demo all --llm-delay 1.5
```

Running against a local OpenAI-compatible endpoint avoids provider rate limits.

## Output modes

- `Default (concise)`:
  - scenario name + description
  - for evaluative demos (`01`–`05`, `07`):
    - `baseline: PASS|FAIL`
    - `compiler: PASS|FAIL`
    - `compiler+compact: PASS|FAIL`
  - expected behavior
  - actual outcome
  - `result: ...` (short deterministic description)
  - for `06_llm_context_compaction`:
    - `context scaling: ...`
    - `compacted transcript: <baseline> → <compacted> chars`
    - `result: ...`
  - when running `all`:
    - blank line between demos
    - final summary with evaluative totals
    - informational summary lines for `06_llm_context_compaction` (non-scored)
- `Verbose (--verbose)`:
  - user inputs
  - compiler decisions and compiled state
  - prompts/messages sent to the LLM
  - output excerpts
  - host checks and final verdict
  - for `06_llm_context_compaction`, also:
    - raw transcript context
    - compiled context
    - compacted transcript context
    - baseline and compiled prompts
    - compacted prompt
    - context and prompt size comparisons (state-only and compacted variants)

### Demo 5: stress ladder (`--turns`)

For Demo 5, `--turns` controls how many distractor turns are inserted between
the original directive and the final prompt.
Longer runs are strict prefix extensions of shorter runs.

Direct demo invocation:

```bash
uv run python demos/05_llm_prompt_drift_vs_state.py --turns 10
uv run python demos/05_llm_prompt_drift_vs_state.py --turns 30
uv run python demos/05_llm_prompt_drift_vs_state.py --turns 60
uv run python demos/05_llm_prompt_drift_vs_state.py --turns 120
uv run python demos/05_llm_prompt_drift_vs_state.py --turns 240
```

Add `--llm-delay 1.25` if your provider throttles requests.

Runner invocation (demo args after `--`):

```bash
uv run python -m demos.run_demo 5 --llm-delay 1.25 -- --turns 120
```
