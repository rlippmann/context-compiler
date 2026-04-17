# Open WebUI Pipe Integration

Open WebUI Pipe Function examples for Context Compiler.

Tested target: Open WebUI `v0.8.12` (latest at time of testing).

## Files

- `open_webui_pipe.py`: basic integration, no preprocessor layer (recommended/default).
- `open_webui_pipe_with_preprocessor.py`: optional/experimental preprocessor layer (heuristic first, then model fallback) before `engine.step(...)`.

## Setup

1. Install integration support in the Open WebUI Python environment:
   - `pip install "context-compiler[integrations]"`
2. Add one of the files above as a Function in Open WebUI.
3. Set `BASE_MODEL_ID` to a valid Open WebUI model id (required).
4. Select the pipe model in chat.

Open WebUI is host-provided runtime infrastructure and must already be installed/configured separately.

If using `open_webui_pipe_with_preprocessor.py`:
- Install preprocessor support in the Open WebUI environment:
  - `pip install "context-compiler[experimental]"`
- Open WebUI executes copied functions from a temp/cached location, so
  preprocessor imports/resources must come from the installed package (not
  repo-relative paths).
- Set `PREPROCESSOR_PROMPT_PROFILE` to `default` for heuristic-first usage.
- Use `llama` only for LLM-only preprocessing with Llama-family models.
- Prompt files are loaded from the installed package prompts (`default`/`llama` profiles).
- Optional: set `PREPROCESSOR_MODEL_ID` to route fallback precompilation through
  a separate model. If unset, fallback uses `BASE_MODEL_ID`.
- Fallback routing is Open WebUI-native (no LiteLLM dependency for this pipe).
- Invalid configured model ids return explicit runtime misconfiguration errors:
  - `BASE_MODEL_ID` not found in Open WebUI models
  - `PREPROCESSOR_MODEL_ID` not found in Open WebUI models

## Limitations

- No persistence.
- No multi-worker or cross-process guarantees.
- No Redis/DB/external storage.
- No Filters or Pipelines.
- No production hardening.
- Version-coupled to Open WebUI internal helper/import paths.

## Manual Validation

Validate clarify short-circuit, passthrough forwarding, update injection with one `[[cc_state]]`, no accumulation across repeated updates, chat isolation with real chat ids, restart state loss, and non-text bypass behavior.

## Behavioral comparisons

**Case 1**

- prompt(s): `clear state` → `change premise to formal tone`
- base model: “To adjust the tone… provide the original content…”
- basic pipe: `No premise exists yet. Use 'set premise ...' first.`
- preprocessor pipe: `No premise exists yet. Use 'set premise ...' first.`
- why this is a real win: lifecycle rule is enforced deterministically; base model drifts into generic rewriting help.

**Case 2**

- prompt(s): `clear state` → `use docker` → `prohibit docker`
- base model: generic Docker/prohibition guidance text
- basic pipe: `'docker' is already in use. Only one policy per item is allowed. Use 'reset policies' to change it.`
- preprocessor pipe: same conflict clarify
- why this is a real win: explicit conflict semantics are preserved instead of conversational interpretation.

**Case 3**

- prompt(s): `clear state` → `use podman instead of docker`
- base model: generic “how to switch to Podman” tutorial
- basic pipe: `No exact policy found for "docker". Replacement requires an exact policy match...`
- preprocessor pipe: same replacement clarify
- why this is a real win: replacement precondition (old item must exist) is enforced.

**Case 4**

- prompt(s): `clear state` → `set premise to concise replies` → `set premise formal tone`
- base model: accepts both as conversational style requests
- basic pipe: `Did you mean 'set premise concise replies'?` then conversational formal-tone rewrite
- preprocessor pipe: `Premise set: Concise replies.` then `Premise already exists...`
- why this is a real win: preprocessor canonicalizes near-miss form and preserves premise-slot semantics end-to-end.

**Case 5**

- prompt(s): `clear state` → `change premise concise replies`
- base model: generic “please clarify changes” response
- basic pipe: `Did you mean 'change premise to concise replies'?`
- preprocessor pipe: `No premise exists yet. Use 'set premise ...' first.`
- why this is a real win: preprocessor upgrades near-miss form and reaches the correct lifecycle clarify state instead of stopping at syntax clarify.
