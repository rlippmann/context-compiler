# Integrations

These examples show how to integrate Context Compiler with external systems.

## LiteLLM (SDK)

Minimal example showing how to run Context Compiler before an LLM call with LiteLLM.

Files:
- Examples (basic + preprocessor): [litellm/README.md](litellm/README.md)

### Requirements

```shell
pip install "context-compiler[integrations]"
export OPENAI_API_KEY=...
```

Checkpoint continuation in these integration examples requires `context-compiler>=0.6.7`.

### Run

See the LiteLLM examples README for setup and usage:
[litellm/README.md](litellm/README.md)

### Behavior

- Context Compiler runs before any LLM call.
- If clarification is required, no LLM call is made.
- Otherwise, compiled state is injected into the prompt before calling the model.

## LiteLLM Proxy

Gateway-level integration using a LiteLLM pre-call hook.

See: [LiteLLM Proxy README](litellm_proxy/README.md)

## Open WebUI Pipe Function

Tested target: Open WebUI `v0.8.12`.

Open WebUI is host-provided runtime infrastructure and must be installed/configured separately.

Files:
- Basic example: [open_webui_pipe.py](openwebui/open_webui_pipe.py)
- With preprocessor: [open_webui_pipe_with_preprocessor.py](openwebui/open_webui_pipe_with_preprocessor.py)

Details: [Open WebUI Pipe Integration README](openwebui/README.md)
