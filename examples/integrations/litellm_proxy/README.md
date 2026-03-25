# LiteLLM Proxy (pre-call hook)

This example shows how to run Context Compiler inside a LiteLLM proxy pre-call hook.
The hook enforces deterministic state handling before any upstream model call.

### Requirements

```shell
pip install 'litellm[proxy]'
export OPENAI_API_KEY=...
```

### Run proxy

```shell
litellm --config config.example.yaml
```

The proxy runs on `http://localhost:4000` by default.
The proxy loads the Context Compiler pre-call hook from `context_compiler_precall_hook.py`.

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

### Note

- The callback path in `config.example.yaml` must be importable.
  Run the proxy from the repo root or set `PYTHONPATH` accordingly.
