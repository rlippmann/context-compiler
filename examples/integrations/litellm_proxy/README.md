# LiteLLM Proxy (pre-call hook)

This example shows how to run Context Compiler inside a LiteLLM proxy pre-call hook.
The hook applies fixed, repeatable state handling before any upstream model call.

Available hook files:

- Basic replay-only hook: `context_compiler_precall_hook.py`
- Preprocessor-enabled hook: `context_compiler_precall_hook_with_preprocessor.py`

### Requirements

```shell
pip install "context-compiler[litellm_proxy]"
export OPENAI_API_KEY=...
```

`litellm_proxy` is intentionally separate from the general `integrations`
extra because this path targets proxy/gateway runtime use.

For `context_compiler_precall_hook_with_preprocessor.py`:

```shell
pip install "context-compiler[experimental]"
```

### Quickstart (copy/paste)

From the repo root:

```shell
pip install "context-compiler[litellm_proxy]"
export OPENAI_API_KEY=...
litellm --config examples/integrations/litellm_proxy/config.example.yaml
```

### Run proxy

Typical startup command (environment-sensitive):

```shell
litellm --config config.example.yaml
```

Hook behavior in this directory is smoke-validated. Proxy server startup with
`litellm --config ...` is environment-sensitive (callback import resolution) and
was not re-validated end-to-end as-is in the latest smoke pass with
`litellm==1.83.7`.

The proxy runs on `http://localhost:4000` by default.
By default, `config.example.yaml` points to the basic replay-only hook.
To use the preprocessor variant, switch the callback path in the config.
Run from the repo root, or set `PYTHONPATH` so `examples.integrations...` callback imports resolve.

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
- Otherwise, compiler state is added as a system message.

Preprocessor-enabled variant behavior:

- Only the latest user transcript message is preprocessed for compiler replay input.
- Heuristic runs first; if no directive is found, LLM fallback is attempted.
- Forwarded upstream request messages are not rewritten (except injected compiler system message).

Optional env vars for preprocessor fallback:

```shell
export PREPROCESSOR_MODEL=openai/gpt-4o-mini
export PREPROCESSOR_PROMPT_PROFILE=default
```

`PREPROCESSOR_MODEL` is optional and defaults to `MODEL`.

For heuristic-first usage, keep `PREPROCESSOR_PROMPT_PROFILE=default`.
Use `llama` only for LLM-only preprocessing with Llama-family models.

### Note

- The callback path in `config.example.yaml` must be importable.
  Run the proxy from the repo root or set `PYTHONPATH` accordingly.

### Troubleshooting

- `ModuleNotFoundError` for callback path: run from repo root, or set `PYTHONPATH=<repo-root>`.
- proxy starts but upstream calls fail: check `OPENAI_API_KEY` and upstream model/provider config in `config.example.yaml`.
- preprocessor fallback issues: `PREPROCESSOR_MODEL` defaults to `MODEL`; set it explicitly only when using a separate fallback model.
