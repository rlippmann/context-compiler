# Demo Results

Canonical reference for the current LLM demo matrix and methodology.

Note: this published matrix predates the `reinjected-state` path added in the 0.7.1 demo/evaluation experiment. It currently reports baseline/compiler/compiler+compact only.

## Scope

- Scored demos: `01`, `02`, `03`, `04`, `05`, `07` (6 total)
- Informational demo: `06_context_compaction` (excluded from PASS/FAIL totals)

Methodology note (2026-05): the demo suite now also includes scored demos `08`
and `09` for rules about when state is allowed to change. The published matrix below predates those additions and
has not yet been fully rerun with the expanded scored set.

## Results Matrix

| Provider Path | Model | Baseline (P/F) | Compiler (P/F) | Compiler+Compact (P/F) |
| :-- | :-- | :--: | :--: | :--: |
| `ollama` | `qwen2.5:7b-instruct` | 4 / 2 | 6 / 0 | 6 / 0 |
| `ollama` | `qwen2.5:14b-instruct` | 4 / 2 | 6 / 0 | 6 / 0 |
| `ollama` | `llama3.1:8b` | 2 / 4 | 6 / 0 | 6 / 0 |
| `openai` | `gpt-4.1` | 4 / 2 | 6 / 0 | 6 / 0 |
| `openai` | `gpt-5` | 4 / 2 | 6 / 0 | 6 / 0 |
| `openai_compatible` | `anthropic/claude-sonnet-4-5-20250929` | 4 / 2 | 6 / 0 | 6 / 0 |
| `openai_compatible` | `anthropic/claude-opus-4-1-20250805` | 4 / 2 | 6 / 0 | 6 / 0 |

## Totals (Derived from Matrix)

- Model runs: `7`
- Scored demos per run: `6`
- Aggregate scored checks per path: `42`

Aggregate pass totals:

- Baseline: `26 / 42`
- Compiler: `42 / 42`
- Compiler+compact: `42 / 42`

## Methodology

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

### Run metadata

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

## Demo 05 Long-Transcript Stress (Exploratory Frontier Runs)

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

## Local Ollama Context-Size Sweep (0.7.1 Experiment)

This section reports the refreshed local-only matrix with the `reinjected-state`
path and explicit context-size ladder runs. Historical hosted-provider matrix rows
above are preserved as originally recorded.

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
