# LiteLLM examples

This directory contains two minimal Context Compiler + LiteLLM integrations:

- `basic.py`: compiler-only flow (no preprocessor)
- `with_preprocessor.py`: heuristic-first preprocessor with optional LLM fallback before `engine.step(...)`

## Requirements

```shell
pip install "context-compiler[integrations]"
export OPENAI_API_KEY=...
```

Checkpoint continuation in these examples requires `context-compiler>=0.6.14`.

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

This near-miss input is expected to clarify rather than be canonicalized.

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
  - default `base_url`: `http://localhost:11434/v1`
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

These files are importable integration references for host applications.

- Import `handle_turn(...)` from either `basic.py` or `with_preprocessor.py`.
- Create and retain an engine instance in host/session state.
- Pass each user input through `handle_turn(user_input, engine)`.
- Optional serialized continuation checkpointing: pass `session_key=...` and
  let the example integration restore before first `engine.step(...)` and
  persist after `update`/`clarify` decisions.
- In this example, checkpoint/session storage is in-memory only.
  Continuation state is limited to the current process lifetime; real restart
  continuity requires external persistence (DB/Redis/etc.).
- Display the returned assistant text.

Note: In these LiteLLM example integrations, update decisions are rendered deterministically and do not call the downstream LLM. This makes state transitions explicit. Production hosts may choose different rendering behavior.

## Troubleshooting

- `litellm is required`: install `context-compiler[integrations]` (or `context-compiler[experimental]` for preprocessor).
- `OPENAI_API_KEY is required in openai mode`: export a key or use `ollama` / explicit endpoint override.
- `Invalid PROVIDER value ...`: set `PROVIDER` to one of `openai`, `ollama`, `openai_compatible`.
- `OPENAI_BASE_URL is required when PROVIDER=openai_compatible`: set an explicit endpoint URL.
- model/provider errors (`Model not found`, provider auth errors): confirm `MODEL` uses LiteLLM format and provider credentials are valid.

## Basic vs preprocessor behavior

- Basic: passes raw user input to `engine.step(...)`.
- With preprocessor: runs heuristic precompiler first.
  - If heuristic returns a directive, that directive is passed to `engine.step(...)`.
  - If heuristic does not produce a directive (`no_directive` or `unknown`), LLM fallback prompt conversion runs.
  - If fallback yields nothing usable or errors, behavior safely remains equivalent to basic.
  - Behavior is reject-first and does not expand directive grammar.

## Example checks

- Near-miss passthrough (`with_preprocessor.py`):
  - `set premise to concise replies` is not rewritten by the precompiler and is passed through unchanged.
  - Engine returns clarify (`Did you mean 'set premise concise replies'?`).
- Lifecycle enforcement (both):
  - `change premise to formal tone` with no premise -> clarify (`set premise ...` first).
- Conflict semantics (both):
  - `use docker` then `prohibit docker` -> conflict clarify.
- Replacement precondition (both):
  - `use podman instead of docker` without prior `use docker` -> replacement clarify.
- Directive-adjacent abstain (`with_preprocessor.py`):
  - `change premise concise replies` is classified as `unknown`, not rewritten, and handled by engine clarify.
