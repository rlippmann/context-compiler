# LiteLLM examples

This directory contains two minimal Context Compiler + LiteLLM integrations:

- `basic.py`: compiler-only flow (no preprocessor)
- `with_preprocessor.py`: heuristic-first preprocessor with optional LLM fallback before `engine.step(...)`

## Requirements

```shell
pip install litellm
pip install context-compiler
export OPENAI_API_KEY=...
```

For `with_preprocessor.py`:

```shell
pip install "context-compiler[experimental]"
```

Optional:

```shell
export MODEL=openai/gpt-4o-mini
export OPENAI_BASE_URL=...
export PREPROCESSOR_PROMPT_PROFILE=default
```

`MODEL` uses LiteLLM format: `<provider>/<model>`.

For heuristic-first usage, keep `PREPROCESSOR_PROMPT_PROFILE=default`.
Use `llama` only for LLM-only preprocessing with Llama-family models.

## Usage pattern

These files are importable integration references for host applications.

- Import `handle_turn(...)` from either `basic.py` or `with_preprocessor.py`.
- Create and retain an engine instance in host/session state.
- Pass each user input through `handle_turn(user_input, engine)`.
- Display the returned assistant text.

## Basic vs preprocessor behavior

- Basic: passes raw user input to `engine.step(...)`.
- With preprocessor: runs heuristic precompiler first.
  - If heuristic returns a directive, that directive is passed to `engine.step(...)`.
  - If heuristic does not resolve to a directive (`no_directive`), LLM fallback prompt conversion runs.
  - If fallback yields nothing usable or errors, behavior safely remains equivalent to basic.

## Example checks

- Near-miss canonicalization (`with_preprocessor.py`):
  - `set premise to concise replies` -> precompiler can canonicalize to `set premise concise replies`.
- Lifecycle enforcement (both):
  - `change premise to formal tone` with no premise -> clarify (`set premise ...` first).
- Conflict semantics (both):
  - `use docker` then `prohibit docker` -> conflict clarify.
- Replacement precondition (both):
  - `use podman instead of docker` without prior `use docker` -> replacement clarify.
- NL upgrade / abstain (`with_preprocessor.py`):
  - `please use docker` may upgrade to `use docker`.
  - `I usually use docker` should abstain (`no directive`).
