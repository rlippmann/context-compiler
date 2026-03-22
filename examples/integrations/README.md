# Integrations

## LiteLLM (SDK)

Minimal example showing how to run Context Compiler before an LLM call with LiteLLM.

### Requirements

```shell
pip install litellm
```
- set OPENAI_API_KEY (or other provider key supported by LiteLLM)

### Run

MODEL uses the format `<provider>/<model>`, e.g. `openai/gpt-4o-mini`.

```shell
MODEL=openai/gpt-4o-mini python litellm_sdk.py
```

### Behavior

- Context Compiler runs before any LLM call.
- If clarification is required, no LLM call is made.
- Otherwise, compiled state is injected into the prompt before calling the model.
