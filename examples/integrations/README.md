# Integrations

These examples show how to integrate Context Compiler with external systems.

## LiteLLM (SDK)

Minimal example showing how to run Context Compiler before an LLM call with LiteLLM.

Files:
- Legacy single-file example: [litellm_sdk.py](litellm_sdk.py)
- New examples (basic + preprocessor): [litellm/README.md](litellm/README.md)

### Requirements

```shell
pip install litellm
export OPENAI_API_KEY=...
```

### Run

MODEL uses the format `<provider>/<model>`, e.g. `openai/gpt-4o-mini`.

```shell
MODEL=openai/gpt-4o-mini python litellm_sdk.py
```

### Behavior

- Context Compiler runs before any LLM call.
- If clarification is required, no LLM call is made.
- Otherwise, compiled state is injected into the prompt before calling the model.

## LiteLLM Proxy

Gateway-level integration using a LiteLLM pre-call hook.

See: [LiteLLM Proxy README](litellm_proxy/README.md)

## Open WebUI Pipe Function

Tested target: Open WebUI `v0.7.2`.

Files:
- Basic example: [open_webui_pipe.py](openwebui/open_webui_pipe.py)
- With preprocessor: [open_webui_pipe_with_preprocessor.py](openwebui/open_webui_pipe_with_preprocessor.py)

Details: [Open WebUI Pipe Integration README](openwebui/README.md)
