# SWE Curated Runs Summary (Compiler Lane)

This report summarizes a small curated subset of SWE-bench tasks comparing baseline prompting to a compiler lane that first converts directive-style instructions into deterministic structured state, then renders the final prompt from that state.

Across 6 models and 6 tasks, this compiler-mediated flow produces higher scores on most task/model pairs, with the strongest gains on tasks where constraints matter most.

## Top-level summary

| Model | Tasks | Compiler Enabled | Scored | + / 0 / - | Avg Delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| `anthropic/claude-opus-4-20250514` | 6 | 6 | 6 | 5 / 0 / 1 | 17.33 |
| `anthropic/claude-sonnet-4-20250514` | 6 | 6 | 6 | 5 / 1 / 0 | 19.33 |
| `openai/gpt-4.1` | 6 | 6 | 6 | 5 / 1 / 0 | 9.83 |
| `openai/gpt-5.4` | 6 | 6 | 6 | 5 / 0 / 1 | 9.17 |
| `ollama/llama3.1:8b`* | 6 | 6 | 5 | 5 / 0 / 0 | 23.80 |
| `ollama/qwen2.5:14b-instruct` | 6 | 6 | 6 | 6 / 0 / 0 | 8.33 |

## Key observations

- Compiler-lane prompting improves scores on most task/model pairs.
- Cross-model consistency is strong on several tasks, especially `psf__requests-1963` and `django__django-13158` (all scored models positive).
- Strongest repeated gains appear on `psf__requests-1963` and `django__django-13158`.
- Notable edge case: `django__django-13964` is mixed (`+29`, `+32`, `0`, `-19`, `+2`, one unscored), indicating sensitivity to how specifically the model reasons about inheritance/PK synchronization details.
- Smaller or less capable models (for example, `llama3.1:8b`) show larger average gains, suggesting structured state is especially helpful when baseline reasoning is weaker.
- `compiled_state` and `rendered_compiler_prompt` were verified deterministic across result files for the same task (e.g., `django__django-13964`, `psf__requests-1963`).

## Task callouts

### `psf__requests-1963`

Per-model score deltas:

- Opus4: `+48`
- Sonnet4: `+31`
- GPT-4.1: `+13`
- GPT-5.4: `+14`
- Llama3.1: `+24`
- Qwen2.5: `+17`

Interpretation: This task shows broad, consistent uplift and appears highly aligned with compiler-style state framing (state propagation constraints across redirect hops).

### `django__django-13158`

Per-model score deltas:

- Opus4: `+10`
- Sonnet4: `+18`
- GPT-4.1: `+21`
- GPT-5.4: `+37`
- Llama3.1: `+23`
- Qwen2.5: `+16`

Interpretation: Very consistent positive movement across all models; the absorbing-element framing for `QuerySet.none()` appears to transfer well.

### `django__django-13964`

Per-model score deltas:

- Opus4: `+29`
- Sonnet4: `+32`
- GPT-4.1: `0`
- GPT-5.4: `-19`
- Llama3.1: `null` (scoring failure in primary run)
- Qwen2.5: `+2`

Interpretation: This task is highly sensitive to constraint specificity. Where performance drops, outputs become more generic FK propagation reasoning and lose precise anchoring to multi-table inheritance parent-link synchronization semantics.

## Caveats

- Results are based on a small curated subset (6 tasks) and are intended as directional evidence, not a full benchmark evaluation.
- Rubric scoring is LLM-based and can vary by model/run even with fixed prompts.
- `llama3.1:8b` should be treated as exploratory for judging: generation can be useful, but rubric output reliability is unstable.
- *`ollama/llama3.1:8b` row has incomplete scoring (`5/6`) due to rubric formatting/validation failures in one task.
- The meaningful regression (`django__django-13964` on GPT-5.4) appears linked to loss of task-specific specificity in rendered compiler-prompt conditioning.
