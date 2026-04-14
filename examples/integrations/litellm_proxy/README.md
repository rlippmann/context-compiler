# LiteLLM Proxy (pre-call hook)

This example shows how to run Context Compiler inside a LiteLLM proxy pre-call hook.
The hook enforces deterministic state handling before any upstream model call.

Available hook files:

- Basic replay-only hook: `context_compiler_precall_hook.py`
- Preprocessor-enabled hook: `context_compiler_precall_hook_with_preprocessor.py`

### Requirements

```shell
pip install 'litellm[proxy]'
pip install context-compiler
export OPENAI_API_KEY=...
```

For `context_compiler_precall_hook_with_preprocessor.py`:

```shell
pip install "context-compiler[experimental]"
```

### Run proxy

```shell
litellm --config config.example.yaml
```

The proxy runs on `http://localhost:4000` by default.
By default, `config.example.yaml` points to the basic replay-only hook.
To use the preprocessor variant, switch the callback path in the config.

### Make a request

```python
from openai import OpenAI

client = OpenAI(
    api_key="anything",
    base_url="http://localhost:4000",
)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "prohibit peanuts"}],
)
```

Or with curl:

```shell
curl http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer anything" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "prohibit peanuts"}]
  }'
```

### Behavior

- User messages are replayed through Context Compiler before the model call.
- If clarification is required, the proxy returns the clarification text as the response instead of calling the model.
- Otherwise, compiled state is injected into a system message.

Preprocessor-enabled variant behavior:

- Only the latest user transcript message is preprocessed for compiler replay input.
- Heuristic runs first; if no directive is found, LLM fallback is attempted.
- Forwarded upstream request messages are not rewritten (except injected compiler system message).

Optional env vars for preprocessor fallback:

```shell
export PREPROCESSOR_MODEL=openai/gpt-4o-mini
export PREPROCESSOR_PROMPT_PROFILE=default
```

For heuristic-first usage, keep `PREPROCESSOR_PROMPT_PROFILE=default`.
Use `llama` only for LLM-only preprocessing with Llama-family models.

### Note

- The callback path in `config.example.yaml` must be importable.
  Run the proxy from the repo root or set `PYTHONPATH` accordingly.
