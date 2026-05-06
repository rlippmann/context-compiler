# Demo Results

Canonical reference for the current LLM demo matrix and methodology.

## Scope

- Scored demos: `01`, `02`, `03`, `04`, `05`, `07` (6 total)
- Informational demo: `06_context_compaction` (excluded from PASS/FAIL totals)

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

Aggregate pass/fail totals:

- Baseline: `26 / 16`
- Compiler: `42 / 0`
- Compiler+compact: `42 / 0`

## Methodology

Primary command:

```bash
uv run python -m demos.run_demo all
```

Provider/model selection is done via environment variables:

- `PROVIDER` (`openai`, `ollama`, `openai_compatible`)
- `MODEL`
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` as required by provider mode

Scoring behavior uses post-audit oracle/checker logic in demos and shared helpers:

- `demos/01_llm_contradiction_clarify.py`
- `demos/02_llm_constraint_guardrail.py`
- `demos/03_llm_premise_guardrail.py`
- `demos/04_llm_tool_denylist_guardrail.py`
- `demos/05_llm_prompt_drift_vs_state.py`
- `demos/07_llm_prompt_vs_state.py`
- shared parsing/helpers in `demos/common.py`

## Interpretation

- Live demo runs are **evidence/smoke tests** across real model/provider behavior.
- Deterministic test suites (unit/property tests) are the **regression authority** for oracle and engine contracts.
