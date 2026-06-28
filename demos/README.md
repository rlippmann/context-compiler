# LLM Demos

These scripts show common reliability limits in LLM app behavior.

They compare normal prompting with an approach where the application tracks
important instructions explicitly instead of relying only on the conversation
history. The scripts are designed to produce consistent results so the
behavior is easy to see.
This demo set shows what users notice: saved authoritative state continues to
affect later turns, and where your app needs deterministic state-transition
rules.

Scored demos now compare four paths:
- baseline
- reinjected-state (application-managed state text injected into the prompt, without compiler semantics)
- compiler-mediated (full transcript + saved compiler state added to the prompt)
- compiler+compact (compacted transcript + saved compiler state added to the prompt)

## Demo overview

| Demo | Behavior | Concept | Most visible with |
| :--: | --- | :--: | --- |
| [03](./03_llm_premise_guardrail.py) | Premise updates stay authoritative | fixed, repeatable premise updates | models that summarize conversation |
| [01](./01_llm_contradiction_clarify.py) | Contradiction blocking | clarification gate | small instruct models |
| [08](./08_llm_replacement_precondition.py) | Replacement precondition | invalid replacement blocked without state mutation | any model |
| [09](./09_llm_pending_clarification.py) | Pending clarification continuation | confirmation-only resolution of suspended mutation | any model |
| [06](./06_llm_context_compaction.py) | Context compaction | saved compiler state replacing transcript context | small or local models |
| [07](./07_llm_prompt_vs_state.py) | Prompt engineering comparison | prompting vs saved compiler state | any model with long transcript sensitivity |
| [02](./02_llm_constraint_guardrail.py) | Policy state stays active across turns | authoritative policy state | small or quantized models |
| [04](./04_llm_tool_denylist_guardrail.py) | Tool governance | application-layer tool gating from saved state | general assistant models |
| [05](./05_llm_prompt_drift_vs_state.py) | Prompt drift | long transcript failure | weaker long-context models ([see Demo 5 note](#demo-5-stress-ladder-turns)) |

Stronger frontier models may show these behaviors less often, but the same
patterns still appear in real applications.

## Requirements

To run the demos from this repository, clone the repo and install the demo dependency extra:

```bash
git clone https://github.com/rlippmann/context-compiler.git
cd context-compiler
pip install "context-compiler[demos]"
```

The `[demos]` extra installs optional dependencies such as LiteLLM. It does not install demo source files into site-packages.

Environment variables (strict provider mode contract):

- `PROVIDER` (optional): `openai` (default), `ollama`, `openai_compatible`
- `MODEL` (optional)
- `OPENAI_API_KEY` (required in normal `openai` mode)
- `OPENAI_BASE_URL` (explicit endpoint override; required for explicit `openai_compatible`)
Note: Demos prefer fixed decoding (`temperature=0`) for reproducible PASS/FAIL behavior.
If a model rejects deterministic sampling parameters on the LiteLLM/OpenAI-compatible path
(for example, some `gpt-5` and Claude paths), the demo client retries once without deterministic
sampling parameters.

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

Anthropic (direct OpenAI-compatible endpoint):

```bash
export PROVIDER=openai_compatible
export OPENAI_BASE_URL=<exact Anthropic compatibility base URL>
export OPENAI_API_KEY=<Anthropic API key>
export MODEL=claude-sonnet-4-6
```

Notes:
- For direct Anthropic usage, `MODEL` should use the endpoint-native model ID.
- Do not use the `anthropic/` prefix unless your endpoint/router expects it.
- This repo passes `MODEL` through unchanged.
- Provide the exact compatibility base URL required by your endpoint, including `/v1` when required.

Anthropic via LiteLLM proxy/gateway:

```bash
export PROVIDER=openai_compatible
export OPENAI_BASE_URL=http://localhost:4000/v1
export OPENAI_API_KEY=<gateway key>
export MODEL=anthropic/claude-sonnet-4-6
```

Notes:
- Provider-prefixed model IDs such as `anthropic/...` are appropriate when the gateway/router expects them.
- Model naming follows the endpoint/router contract.

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

Set Ollama context size (`num_ctx`) from the runner:

```bash
uv run python -m demos.run_demo all --context-size 8192
uv run python -m demos.run_demo all --context-size 4096
uv run python -m demos.run_demo all --context-size 2048
```

`--context-size` is intended for local Ollama runs (`PROVIDER=ollama`) and maps to
Ollama `num_ctx`. Using it with unsupported providers fails with a clear error.
When `--context-size` is omitted on Ollama runs, the runner attempts best-effort
default context discovery and reports either a discovered numeric default
(`Context size: <n> (default)`) or `Context size: default` if numeric discovery
is unavailable.

## Results

This README describes the current demo suite in this repository.

The published results page in [docs/demos-results.md](../docs/demos-results.md)
includes:

- a current 2026-06 verification matrix covering frontier-provider reruns and local Ollama runs
- the older historical 0.6.15 matrix for the earlier 6-demo scored set

Notes:
- There are **8 scored demos** (`01`–`05`, `07`, `08`, `09`). `06_context_compaction` is informational and excluded from PASS/FAIL totals.
- Anthropic runs in this repo are executed through the `openai_compatible` provider path.
- `PASS` means the demo-specific expected-behavior check for that path succeeded; `FAIL` means it did not.
- `reinjected-state` can be enough for some persistence cases; this comparison shows where app-side state rules add value.
- Scored checks focus on app-side state rules (for example blocked mutation and confirmation-only resolution), not model prose quality. `reinjected-state` remains plain text injection only.
- Interpretation:
- Demos `01`-`05` and `07` mostly test persistence and policy-following behavior across turns.
- Demos `08`/`09` test rules for when state is allowed to change.
- Demos `08` and `09` cover cases prompt text does not implement by itself, such as checking whether replacement is allowed and waiting for confirmation before saving changes.
- Plain prompt reinjection can produce reasonable answers, but it does not run these checks by itself.
- Similar outcomes across models in `08`/`09` reflect app behavior limits, not model leaderboard ranking.

### Demo 05 example (prompt drift under longer context)

Demo 05 measures prompt drift versus saved compiler state on a longer transcript.
Representative run: `PROVIDER=ollama MODEL='ollama/llama3.1:8b' uv run python demos/05_llm_prompt_drift_vs_state.py --turns 30`

```text
05_prompt_drift — preserve premise across long transcript
Final user request:
Now give me a dinner plan. First line must be PREMISE:<value>. Keep the plan consistent with that premise.

Compiler-mediated output:
PREMISE:vegetarian curry
Here's a short dinner plan:

baseline: FAIL
reinjected-state: PASS
compiler: PASS
compiler+compact: PASS
```

The baseline lost the earlier rule under the longer transcript, while reinjected-state and both compiler-mediated paths kept the saved premise in this run.

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
  - for evaluative demos (`01`–`05`, `07`, `08`, `09`):
    - `baseline: PASS|FAIL`
    - `reinjected-state: PASS|FAIL`
    - `compiler: PASS|FAIL`
    - `compiler+compact: PASS|FAIL`
  - expected behavior
  - actual outcome
  - `result: ...` (short fixed, repeatable description)
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
  - compiler decisions and saved compiler state
  - prompts/messages sent to the LLM
  - output excerpts
  - host checks and final verdict
  - for `06_llm_context_compaction`, also:
    - raw transcript context
    - context with saved compiler state
    - compacted transcript context
    - baseline and compiler-state prompts
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
