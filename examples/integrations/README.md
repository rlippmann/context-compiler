# Integrations

These examples show how to use Context Compiler inside external app runtimes.

## LiteLLM (SDK)

Minimal example showing how to run Context Compiler before sending a request to the LLM with LiteLLM.

Files:
- Examples (basic + preprocessor): [litellm/README.md](litellm/README.md)

### Requirements

```shell
pip install "context-compiler[integrations]"
export OPENAI_API_KEY=...
export PROVIDER=openai
```

Checkpoint continuation in these integration examples requires `context-compiler>=0.6.14`.

### Run

See the LiteLLM examples README for setup and usage:
[litellm/README.md](litellm/README.md)

### Behavior

- Context Compiler runs before each LLM call.
- If result is `clarify`, show the question and do not call the LLM.
- If result is `passthrough`, send normal user input.
- If result is `update`, use updated state and call the model with saved state in the prompt.

## LiteLLM Proxy

Gateway-level integration using a LiteLLM pre-call hook.

See: [LiteLLM Proxy README](litellm_proxy/README.md)

## Open WebUI Pipe Function

Tested target: Open WebUI `v0.8.12`.

Open WebUI is a separate runtime and must be installed/configured separately.

Files:
- Basic example: [open_webui_pipe.py](openwebui/open_webui_pipe.py)
- With preprocessor: [open_webui_pipe_with_preprocessor.py](openwebui/open_webui_pipe_with_preprocessor.py)

Details: [Open WebUI Pipe Integration README](openwebui/README.md)
