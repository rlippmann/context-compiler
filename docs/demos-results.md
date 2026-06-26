# Demo Results

Published LLM demo evidence for this repository.

This document preserves earlier published results and also records newer reruns
where available.

## Current Frontier Rerun (2026-06)

This rerun covers the current 8-demo scored set:

- scored demos: `01`-`05`, `07`, `08`, `09`
- informational demo: `06_context_compaction`

### Frontier Results Matrix

| Provider Path | Model | Baseline (P/F) | Reinjected-state (P/F) | Compiler (P/F) | Compiler+Compact (P/F) |
| :-- | :-- | :--: | :--: | :--: | :--: |
| `openai` | `gpt-4.1` | 4 / 4 | 6 / 2 | 8 / 0 | 8 / 0 |
| `openai` | `gpt-5` | 3 / 5 | 6 / 2 | 8 / 0 | 8 / 0 |
| `openai_compatible` | `anthropic/claude-sonnet-4-6` | 3 / 5 | 5 / 3 | 8 / 0 | 8 / 0 |
| `openai_compatible` | `anthropic/claude-opus-4-1` | 4 / 4 | 6 / 2 | 8 / 0 | 8 / 0 |

### Frontier Totals (Derived from Matrix)

- Model runs: `4`
- Scored demos per run: `8`
- Aggregate scored checks per path: `32`

Aggregate pass totals:

- Baseline: `14 / 32`
- Reinjected-state: `23 / 32`
- Compiler: `32 / 32`
- Compiler+compact: `32 / 32`

### Frontier Run Metadata

- Date: 2026-06-26
- Context Compiler: working tree before Python `0.8.0` release
- Command family: `uv run python -m demos.run_demo all`
- Artifact source: `/tmp/context-compiler-demo-results`

### Frontier Notes

- The current scored set adds `08` and `09`, which test app-side state-transition
  rules rather than general response quality.
- A third-pass full rerun corrected the earlier `gpt-4.1` Demo `02` compiler
  failure; the current published `gpt-4.1` row is now `8 / 0` on both compiler
  paths.
- A fresh full rerun corrected an earlier stale `gpt-5` Demo `02` summary; the
  current published `gpt-5` row is `6 / 2` for `reinjected-state` and `8 / 0`
  for both compiler paths.
- Both Anthropic-compatible reruns completed with `8 / 0` on both compiler paths.
- The file `claude-sonnet-4-6.txt` is a setup probe from parameter/config
  discovery, not one of the four scored frontier runs summarized above.

## Historical Published Matrix (0.6.15)

Historical LLM demo evidence for an earlier published matrix.

This section is not the current release-evidence summary for the repository's
present demo suite. It preserves earlier published results so readers can see
what was measured at the time.

The matrix below:

- was recorded against Context Compiler `0.6.15`
- covers the earlier scored set `01`-`05`, `07` only
- predates the later scored additions `08` and `09`
- predates the published `reinjected-state` comparison in the cross-model matrix

## Historical Scope

- Scored demos: `01`, `02`, `03`, `04`, `05`, `07` (6 total)
- Informational demo: `06_context_compaction` (excluded from PASS/FAIL totals)

Current repository note (2026-06): the demo suite now also includes scored demos
`08` and `09` for rules about when state is allowed to change. No published
cross-model rerun is included here for that expanded scored set.

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

## Historical Totals (Derived from Matrix)

- Model runs: `7`
- Scored demos per run: `6`
- Aggregate scored checks per path: `42`

Aggregate pass totals:

- Baseline: `26 / 42`
- Compiler: `42 / 42`
- Compiler+compact: `42 / 42`

## Historical Methodology

Primary command:

```bash
uv run python -m demos.run_demo all
```

Provider/model selection is done via environment variables:

- `PROVIDER` (`openai`, `ollama`, `openai_compatible`)
- `MODEL`
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` as required by provider mode

Historical Anthropic rows below were run through an OpenAI-compatible path using
provider-prefixed model IDs. For new runs, model naming follows the configured
endpoint or gateway contract.

Scoring behavior uses post-audit oracle/checker logic in demos and shared helpers:

- `demos/01_llm_contradiction_clarify.py`
- `demos/02_llm_constraint_guardrail.py`
- `demos/03_llm_premise_guardrail.py`
- `demos/04_llm_tool_denylist_guardrail.py`
- `demos/05_llm_prompt_drift_vs_state.py`
- `demos/07_llm_prompt_vs_state.py`
- `demos/08_llm_replacement_precondition.py`
- `demos/09_llm_pending_clarification.py`
- shared parsing/helpers in `demos/common.py`

Scored checks focus on app-side state rules rather than preferred wording in
model outputs. The `reinjected-state` path is plain state text injection and
does not include compiler checks like replacement preconditions or pending
confirmation handling.

### Historical Run Metadata

- Date: 2026-05-06
- Context Compiler: 0.6.15
- Command: `uv run python -m demos.run_demo all`
- Demo 05 turn count in this matrix: default setting (`--turns` omitted)

## Interpretation

- Live demo runs are **evidence/smoke tests** across real model/provider behavior.
- Deterministic test suites (unit/property tests) are the **regression authority** for oracle and engine contracts.
- Persistence demos and state-change-rule demos should be interpreted differently.
- Demos `01`-`05` and `07` mostly test persistence and policy-following under transcript pressure.
- Demos `08`/`09` test rules for when state is allowed to change.
- Demos `08` and `09` cover cases prompt text does not implement by itself, such as checking whether replacement is allowed and waiting for confirmation before saving changes.
- Plain prompt reinjection can produce reasonable answers, but it does not run these checks by itself.
- Demos `08`/`09` are not general LLM quality benchmarks. Baseline and reinjected-state can produce plausible text and still `FAIL` when those app-side checks are missing.

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
provide explicit state-change rules.

## Historical Local Ollama Context-Size Sweep (0.7.1 Experiment)

This section reports the refreshed local-only matrix with the `reinjected-state`
path and explicit context-size ladder runs. Historical hosted-provider matrix
rows above remain as originally recorded.

### Commands Run

```bash
PROVIDER=ollama MODEL=ollama/llama3.1:8b uv run python -m demos.run_demo all --context-size 8192
PROVIDER=ollama MODEL=ollama/llama3.1:8b uv run python -m demos.run_demo all --context-size 4096
PROVIDER=ollama MODEL=ollama/llama3.1:8b uv run python -m demos.run_demo all --context-size 2048

PROVIDER=ollama MODEL=ollama/qwen2.5:7b-instruct uv run python -m demos.run_demo all --context-size 8192
PROVIDER=ollama MODEL=ollama/qwen2.5:7b-instruct uv run python -m demos.run_demo all --context-size 4096
PROVIDER=ollama MODEL=ollama/qwen2.5:7b-instruct uv run python -m demos.run_demo all --context-size 2048

PROVIDER=ollama MODEL=ollama/qwen2.5:14b-instruct uv run python -m demos.run_demo all --context-size 8192
PROVIDER=ollama MODEL=ollama/qwen2.5:14b-instruct uv run python -m demos.run_demo all --context-size 4096
PROVIDER=ollama MODEL=ollama/qwen2.5:14b-instruct uv run python -m demos.run_demo all --context-size 2048
```

### Results Matrix (Scored Demos 01-05, 07)

| Provider | Model | Context size | Baseline (P/F) | Reinjected-state (P/F) | Compiler (P/F) | Compiler+compact (P/F) |
| :-- | :-- | :--: | :--: | :--: | :--: | :--: |
| `ollama` | `llama3.1:8b` | `8192` | 2 / 4 | 5 / 1 | 6 / 0 | 6 / 0 |
| `ollama` | `llama3.1:8b` | `4096` | 2 / 4 | 5 / 1 | 6 / 0 | 6 / 0 |
| `ollama` | `llama3.1:8b` | `2048` | 2 / 4 | 5 / 1 | 6 / 0 | 6 / 0 |
| `ollama` | `qwen2.5:7b-instruct` | `8192` | 4 / 2 | 6 / 0 | 6 / 0 | 6 / 0 |
| `ollama` | `qwen2.5:7b-instruct` | `4096` | 4 / 2 | 6 / 0 | 6 / 0 | 6 / 0 |
| `ollama` | `qwen2.5:7b-instruct` | `2048` | 4 / 2 | 6 / 0 | 6 / 0 | 6 / 0 |
| `ollama` | `qwen2.5:14b-instruct` | `8192` | 4 / 2 | 5 / 1 | 6 / 0 | 6 / 0 |
| `ollama` | `qwen2.5:14b-instruct` | `4096` | 4 / 2 | 5 / 1 | 6 / 0 | 6 / 0 |
| `ollama` | `qwen2.5:14b-instruct` | `2048` | 4 / 2 | 5 / 1 | 6 / 0 | 6 / 0 |

### Concise Observations

- `compiler` and `compiler+compact` were stable at `6 / 0` across all models and all context sizes.
- `reinjected-state` stayed competitive:
  - `6 / 0` for `qwen2.5:7b-instruct`
  - `5 / 1` for `llama3.1:8b` and `qwen2.5:14b-instruct`
- `baseline` varied by model but not by context size in this sweep:
  - `2 / 4` for `llama3.1:8b`
  - `4 / 2` for both Qwen models
- For monitored demos:
  - Demo `02` was the most persistent failure point for baseline, and remained a reinjected failure on `llama3.1:8b` and `qwen2.5:14b-instruct`.
  - Demo `05` only failed baseline on `llama3.1:8b`; other paths passed.
  - Demo `01` baseline failed on `llama3.1:8b` but passed on Qwen models.
  - Demo `07` passed on all paths for all model/context combinations in this run set.
