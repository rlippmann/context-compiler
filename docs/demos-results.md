# Demo Results

Published LLM demo evidence for this repository.

This page answers a practical release question: does Context Compiler work, and
what evidence supports that claim?

For runnable application-layer enforcement-point integrations, see
[`context-compiler-example-integrations`](https://github.com/rlippmann/context-compiler-example-integrations).

## Current Verification Results (2026-06)

Current release-facing verification covers the current 8-demo scored set:

- scored demos: `01`-`05`, `07`, `08`, `09`
- informational demo: `06_context_compaction`

### Current Results Matrix

| Provider Path | Model | Context | Baseline (P/F) | Reinjected-state (P/F) | Compiler (P/F) | Compiler+Compact (P/F) |
| :-- | :-- | :-- | :--: | :--: | :--: | :--: |
| `openai` | `gpt-4.1` | standard | 4 / 4 | 6 / 2 | 8 / 0 | 8 / 0 |
| `openai` | `gpt-5` | standard | 3 / 5 | 6 / 2 | 8 / 0 | 8 / 0 |
| `openai_compatible` | `anthropic/claude-sonnet-4-6` | standard | 3 / 5 | 5 / 3 | 8 / 0 | 8 / 0 |
| `openai_compatible` | `anthropic/claude-opus-4-1` | standard | 4 / 4 | 6 / 2 | 8 / 0 | 8 / 0 |
| `ollama` | `llama3.1:8b` | `131072 (default)` | 2 / 6 | 6 / 2 | 8 / 0 | 8 / 0 |
| `ollama` | `qwen2.5:7b-instruct` | `32768 (default)` | 4 / 4 | 6 / 2 | 8 / 0 | 8 / 0 |
| `ollama` | `qwen2.5:14b-instruct` | `32768 (default)` | 4 / 4 | 5 / 3 | 8 / 0 | 8 / 0 |

### Current Totals

- Model runs: `7`
- Scored demos per run: `8`
- Aggregate scored checks per path: `56`

- Baseline: `24 / 56`
- Reinjected-state: `40 / 56`
- Compiler: `56 / 56`
- Compiler+compact: `56 / 56`

### Interpretation

- Current verification shows `56 / 56` passes on both compiler paths across the hosted-provider and local Ollama rows.
- Baseline and reinjected-state vary by model, but the compiler-mediated paths stay perfect across all listed current runs.
- The current Ollama rows are current 8-demo reruns recorded at each model's discovered default context size.
- `PASS` means the demo-specific expected behavior succeeded for that path.
- `baseline` reflects model behavior without added saved-state authority.
- `reinjected-state` is a prompt-only baseline: plain application-managed state text added to the prompt, without authority semantics.
- `compiler` and `compiler+compact` reflect compiler-mediated authority behavior rather than prompt-only persistence.

### Methodology

- Main run command: `uv run python -m demos.run_demo all`
- Provider selection uses `PROVIDER`, `MODEL`, and provider-specific endpoint or key configuration.
- The current matrix combines standard hosted/frontier runs and current local Ollama runs on the same 8-demo scored set.
- Ollama context values shown in the current matrix are discovered defaults reported by the runner, not a fixed context-size sweep.
- `06_context_compaction` is informational and excluded from PASS/FAIL totals.

## Historical Results (0.6.15)

Historical LLM demo evidence for an earlier published matrix.

- Scored demos: `01`, `02`, `03`, `04`, `05`, `07` (6 total)
- Informational demo: `06_context_compaction` (excluded from PASS/FAIL totals)

## Historical Results Matrix

| Provider Path | Model | Baseline (P/F) | Compiler (P/F) | Compiler+Compact (P/F) |
| :-- | :-- | :--: | :--: | :--: |
| `ollama` | `qwen2.5:7b-instruct` | 4 / 2 | 6 / 0 | 6 / 0 |
| `ollama` | `qwen2.5:14b-instruct` | 4 / 2 | 6 / 0 | 6 / 0 |
| `ollama` | `llama3.1:8b` | 2 / 4 | 6 / 0 | 6 / 0 |
| `openai` | `gpt-4.1` | 4 / 2 | 6 / 0 | 6 / 0 |
| `openai` | `gpt-5` | 4 / 2 | 6 / 0 | 6 / 0 |
| `openai_compatible` | `anthropic/claude-sonnet-4-5-20250929` | 4 / 2 | 6 / 0 | 6 / 0 |
| `openai_compatible` | `anthropic/claude-opus-4-1-20250805` | 4 / 2 | 6 / 0 | 6 / 0 |

## Historical Totals

- Model runs: `7`
- Scored demos per run: `6`
- Aggregate scored checks per path: `42`

Aggregate pass totals:

- Baseline: `26 / 42`
- Compiler: `42 / 42`
- Compiler+compact: `42 / 42`

## Historical Methodology

- Main run command: `uv run python -m demos.run_demo all`
- `PROVIDER` (`openai`, `ollama`, `openai_compatible`)
- `MODEL`
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` as required by provider mode

- Date: 2026-05-06
- Context Compiler: 0.6.15
- Demo 05 turn count in this matrix: default setting (`--turns` omitted)

## Historical Demo 05 Long-Transcript Stress (Exploratory Frontier Runs)

Additional exploratory runs extended Demo 05 to higher transcript lengths for selected
frontier models. These runs are separate from the full cross-model matrix above, which
records the standard scored demo configuration.

- Models: `gpt-4.1` and `claude-sonnet-4-6` (OpenAI-compatible path)
- Turn counts: up to `240`
- In those exploratory runs, `reinjected-state`, `compiler`, and `compiler+compact`
  continued to preserve premise-consistent behavior.

This is exploratory evidence, not benchmark authority. Reinjection can be
enough in some persistence scenarios, while compiler-mediated paths still
provide authority semantics such as replacement preconditions, blocked
mutations, and pending confirmation handling.
