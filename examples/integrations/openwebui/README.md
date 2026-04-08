# Open WebUI Pipe Integration

Open WebUI Pipe Function examples for Context Compiler.

Tested target: Open WebUI `v0.7.2`.

## Files

- `open_webui_pipe.py`: basic integration, no preprocessor layer.
- `open_webui_pipe_with_preprocessor.py`: heuristic-first preprocessor plus LLM fallback before `engine.step(...)`.

## Setup

1. Install `context-compiler` in the Open WebUI Python environment.
2. Add one of the files above as a Function in Open WebUI.
3. Set `BASE_MODEL_ID` to a valid Open WebUI model id (required).
4. Select the pipe model in chat.

If using `open_webui_pipe_with_preprocessor.py`:
- Set `PREPROCESSOR_MODEL_ID` to a model available to LiteLLM.
- Set `PREPROCESSOR_PROMPT_PROFILE` to `default` or `llama`.
- Ensure `OPENAI_API_KEY` is set (and `OPENAI_BASE_URL` if needed).
- Prompt files are loaded from `experimental/preprocessor/prompts/default.txt` and `experimental/preprocessor/prompts/llama.txt`.

## Limitations

- No persistence.
- No multi-worker or cross-process guarantees.
- No Redis/DB/external storage.
- No Filters or Pipelines.
- No production hardening.
- Version-coupled to Open WebUI internal helper/import paths.

## Manual Validation

Validate clarify short-circuit, passthrough forwarding, update injection with one `[[cc_state]]`, no accumulation across repeated updates, chat isolation with real chat ids, restart state loss, and non-text bypass behavior.
