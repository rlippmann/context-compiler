# Open WebUI Pipe Integration

Minimal Open WebUI Pipe Function integration for Context Compiler. It maps compiler `Decision` output into Open WebUI request flow with a deliberately small, focused implementation.

Tested target: Open WebUI `v0.7.2`.

## Setup

1. Install `context-compiler` in the Open WebUI Python environment.
2. Add `open_webui_pipe.py` as a Function in Open WebUI.
3. Set `BASE_MODEL_ID` to a valid Open WebUI model id.
4. Select the pipe model in chat.

Main behavioral documentation lives in [`open_webui_pipe.py`](open_webui_pipe.py) docstrings.

## Limitations

- No persistence.
- No multi-worker or cross-process guarantees.
- No Redis/DB/external storage.
- No Filters or Pipelines.
- No production hardening.
- Version-coupled to Open WebUI internal helper/import paths.

## Manual Validation

Validate clarify short-circuit, passthrough forwarding, update injection with one `[[cc_state]]`, no accumulation across repeated updates, chat isolation with real chat ids, restart state loss, and non-text bypass behavior.
