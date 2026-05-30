# LiteLLM Proxy (pre-call hook)

This example shows how to run Context Compiler inside a LiteLLM proxy pre-call hook.
The hook applies fixed state rules before any upstream model call.

Available hook files:

- Basic replay-only hook: `context_compiler_precall_hook.py`
- Preprocessor-enabled hook: `context_compiler_precall_hook_with_preprocessor.py`

## Requirements

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

## Quickstart (copy/paste)

From the repo root:

```shell
pip install "context-compiler[litellm_proxy]"
export OPENAI_API_KEY=...
litellm --config examples/integrations/litellm_proxy/config.example.yaml
```

`config.example.yaml` includes both OpenAI and Ollama model definitions.
Use the Ollama model entry for local testing without API credentials.

## Run proxy

Typical startup command (environment-sensitive):

```shell
litellm --config config.example.yaml
```

Hook behavior and proxy startup were re-validated end-to-end with
`litellm==1.88.2`.

Validated behaviors:

- passthrough: upstream model called normally
- update: compiler state injected before upstream model call
- clarify: request blocked before upstream model call and surfaced as HTTP 400

The proxy runs on `http://localhost:4000` by default.
By default, `config.example.yaml` points to the basic replay-only hook.
To use the preprocessor variant, switch the callback path in the config.

## Make a request

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

## Behavior

- User messages are replayed through Context Compiler before the model call.
- If result is `clarify`, the proxy does not call the model and LiteLLM surfaces the clarification as an HTTP 400 response.
- If result is `passthrough`, the proxy forwards the request normally.
- If result is `update`, the proxy injects compiler state as a system message and then calls the model.

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

## Note

- The callback path in `config.example.yaml` must be importable by LiteLLM.

## Troubleshooting

- Callback import failures: verify the callback path configured in `config.example.yaml` is importable in the current LiteLLM environment.
- proxy starts but upstream calls fail: check `OPENAI_API_KEY` and upstream model/provider config in `config.example.yaml`.
- preprocessor fallback issues: `PREPROCESSOR_MODEL` defaults to `MODEL`; set it explicitly only when using a separate fallback model.
