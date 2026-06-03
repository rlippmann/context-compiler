# LiteLLM examples

This directory contains three small Context Compiler + LiteLLM integration examples:

- `basic.py`: compiler-only flow (no preprocessor)
- `response_format.py`: host-side LiteLLM `response_format` selection from saved compiler state
- `with_preprocessor.py`: heuristic-first preprocessor with optional LLM fallback before `engine.step(...)`

## Requirements

```shell
pip install "context-compiler[integrations]"
export OPENAI_API_KEY=...
```

Checkpoint continuation in these examples requires `context-compiler>=0.7.0`.

For `with_preprocessor.py`:

```shell
pip install "context-compiler[experimental]"
```

## Quickstart (copy/paste)

```shell
pip install "context-compiler[integrations]"
export OPENAI_API_KEY=...
export MODEL=openai/gpt-4o-mini
python - <<'PY'
from context_compiler import create_engine
from examples.integrations.litellm.basic import handle_turn
engine = create_engine()
print(handle_turn("set premise concise replies", engine))
PY
```

For preprocessor behavior:

```shell
pip install "context-compiler[experimental]"
export OPENAI_API_KEY=...
export MODEL=openai/gpt-4o-mini
python - <<'PY'
from context_compiler import create_engine
from examples.integrations.litellm.with_preprocessor import handle_turn
engine = create_engine()
print(handle_turn("set premise to concise replies", engine))
PY
```

This near-miss input should return `clarify` instead of being rewritten.

For host-side response shape selection:

```shell
pip install "context-compiler[integrations]"
export OPENAI_API_KEY=...
export MODEL=openai/gpt-4o-mini
python - <<'PY'
from context_compiler import create_engine
from examples.integrations.litellm.response_format import plan_turn
engine = create_engine()
engine.step("use compact_summary")
print(plan_turn("Summarize the release notes.", engine))
PY
```

## Environment configuration

Required (normal `openai` mode):

```shell
export OPENAI_API_KEY=...
```

Optional:

```shell
export PROVIDER=openai
export MODEL=openai/gpt-4o-mini
export PREPROCESSOR_MODEL=openai/gpt-4o-mini
export OPENAI_BASE_URL=...
export PREPROCESSOR_PROMPT_PROFILE=default
```

Provider mode contract (`PROVIDER`) is strict:

- `openai`
- `ollama`
- `openai_compatible`

Unknown values hard fail with a validation error.

Resolution precedence:

1. `OPENAI_BASE_URL` override
2. `PROVIDER`
3. default (`openai`)

Operational behavior by mode:

- `openai`
  - default `base_url`: `https://api.openai.com/v1`
  - requires `OPENAI_API_KEY`
- `ollama`
  - default `base_url`: `http://localhost:11434`
  - API key optional
- `openai_compatible`
  - requires `OPENAI_BASE_URL` when explicitly selected with `PROVIDER`
  - API key requirement depends on endpoint

Startup emits one concise config line showing resolved `mode`, `base_url`, `model`,
and resolution `source` (`default`, `PROVIDER`, or `OPENAI_BASE_URL override`).

`MODEL` and `PREPROCESSOR_MODEL` use LiteLLM format: `<provider>/<model>`.
`PREPROCESSOR_MODEL` is optional and defaults to `MODEL`.

For heuristic-first usage, keep `PREPROCESSOR_PROMPT_PROFILE=default`.
Use `llama` only for LLM-only preprocessing with Llama-family models.

## Usage pattern

You can import these files as integration references in host applications.

- Import `handle_turn(...)` from either `basic.py` or `with_preprocessor.py`.
- Create and retain an engine instance in host/session state.
- Pass each user input through `handle_turn(user_input, engine)`.
- Optional checkpointing: pass `session_key=...`.
  The example restores checkpoint data before the first `engine.step(...)` and
  saves checkpoint data after `update`/`clarify`.
- In this example, checkpoint/session storage is in-memory only.
  State lasts only for the current process. To survive restarts, store
  checkpoints in external storage (DB/Redis/etc.).
- Display the returned assistant text.

Note: In these LiteLLM examples, `update` is rendered locally and does not call
the downstream LLM. This makes state changes explicit. Production apps may
choose different rendering behavior.

## Response format example boundary

`response_format.py` shows a different integration boundary from prompt reinjection:

- Context Compiler owns authoritative state.
- The host reads saved policy state and selects a LiteLLM `response_format` or omits it.
- LiteLLM owns model invocation and provider behavior.
- Context Compiler does not call LiteLLM on its own.
- Context Compiler does not validate model output.
- Context Compiler does not generate schemas dynamically.
- This is application-layer use of authoritative state, not compiler semantics.

## Troubleshooting

- `litellm is required`: install `context-compiler[integrations]` (or `context-compiler[experimental]` for preprocessor).
- `OPENAI_API_KEY is required in openai mode`: export a key or use `ollama` / explicit endpoint override.
- `Invalid PROVIDER value ...`: set `PROVIDER` to one of `openai`, `ollama`, `openai_compatible`.
- `OPENAI_BASE_URL is required when PROVIDER=openai_compatible`: set an explicit endpoint URL.
- model/provider errors (`Model not found`, provider auth errors): confirm `MODEL` uses LiteLLM format and provider credentials are valid.

## Basic vs preprocessor behavior

- Basic: passes raw user input to `engine.step(...)`.
- With preprocessor: runs heuristic preprocessor first.
  - If heuristic returns a directive, that directive is passed to `engine.step(...)`.
  - If heuristic does not produce a directive (`no_directive` or `unknown`), LLM fallback prompt conversion runs.
  - If fallback yields nothing usable or errors, behavior safely remains equivalent to basic.
  - If `engine.has_pending_clarification()` is true, bypass preprocessing and pass raw input directly to `engine.step(...)`.
  - Behavior is reject-first and does not broaden the directive grammar.

Decision flow in both examples:
- `passthrough`: call the model with normal input.
- `clarify`: show `prompt_to_user`; do not treat state as changed.
- `update`: state changed; use updated state for the next model call.

Decision flow in `response_format.py`:
- `passthrough`: let the host decide whether to send `response_format`.
- `clarify`: show `prompt_to_user`; do not call LiteLLM.
- `update`: state changed; the next host request may use a different `response_format`.

## Example checks

- Near-miss passthrough (`with_preprocessor.py`):
  - `set premise to concise replies` is not rewritten by the preprocessor and is passed through unchanged.
  - Engine returns clarify (`Did you mean 'set premise concise replies'?`).
- Lifecycle enforcement (both):
  - `change premise to formal tone` with no premise -> clarify (`set premise ...` first).
- Conflict behavior (both):
  - `use docker` then `prohibit docker` -> conflict clarify.
- Replacement precondition (both):
  - `use podman instead of docker` without prior `use docker` -> replacement clarify.
- Directive-adjacent abstain (`with_preprocessor.py`):
  - `change premise concise replies` is classified as `unknown`, not rewritten, and handled by engine clarify.
- Host-side request shaping (`response_format.py`):
  - `use compact_summary` -> host selects compact-summary `response_format`.
  - `use action_plan` -> host selects action-plan `response_format`.
  - `prohibit compact_summary` -> host omits that `response_format`.

## Optional smoke run for `response_format.py`

```shell
export RUN_LITELLM_SMOKE=1
export PROVIDER=ollama
export MODEL=ollama/qwen2.5:1.5b-instruct
uv run python examples/integrations/litellm/response_format.py
```

For local Ollama smoke runs in this repo, `PROVIDER=ollama` is required. A
`MODEL=ollama/...` value by itself still follows the default OpenAI provider
path.
