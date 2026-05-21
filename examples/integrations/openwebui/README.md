# Open WebUI Pipe Integration

Examples of Open WebUI Pipe Functions that run Context Compiler.

Tested target: Open WebUI `v0.8.12` (latest at time of testing).
Runtime-validated on stock Docker Open WebUI with a real backend model provider.

Compatibility note: OpenWebUI `0.9.x` changed `Users.get_user_by_id` to async.
These examples support both sync (`0.8.x`) and async (`0.9.x`) user lookup.

## Files

- `open_webui_pipe.py`: basic integration, no preprocessor layer (recommended/default).
- `open_webui_pipe_with_preprocessor.py`: optional/experimental preprocessor layer (rule-based check first, then optional model fallback) before `engine.step(...)`.

## Setup

The minimal pipe path below is the easiest first-run flow and was runtime-validated in Docker via API flow with a real backend model.

1. Import `open_webui_pipe.py` (recommended/default) as a Function by URL.
2. Open WebUI installs `context-compiler>=0.6.14` from the function frontmatter requirements.
3. Enable the function.
4. Set `BASE_MODEL_ID` to a valid Open WebUI model id (required).
5. Select the pipe model in chat.

Open WebUI is host-provided runtime infrastructure and must already be installed/configured separately.
Open WebUI also needs at least one real backend model/provider configured (for example Ollama or OpenAI) so `BASE_MODEL_ID` resolves to an actual model.
Note: The `PROVIDER` environment contract used in LiteLLM examples/demos does not apply to OpenWebUI. OpenWebUI manages providers via its own connection settings and model IDs.

Checkpoint continuation in these examples requires `context-compiler>=0.6.14`.

### Model configuration

- Open: `http://localhost:3000/admin/functions`
- Verify `BASE_MODEL_ID` matches an existing Open WebUI model id exactly.
- Example:
  - `BASE_MODEL_ID = llama3.1:8b`
- Model ids are configured in: `Admin Panel → Settings → Models`

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
- The heuristic preprocessor is intentionally conservative/high-precision and
  may abstain on mixed-prose natural language (for example, `i think we should
  use docker`). In those cases, behavior may remain passthrough unless fallback
  precompilation returns a validated canonical directive.
- Invalid configured model ids return explicit runtime misconfiguration errors:
  - `BASE_MODEL_ID` not found in Open WebUI models
  - `PREPROCESSOR_MODEL_ID` not found in Open WebUI models

### Docker/manual install fallback

If frontmatter dependency installs are disabled, offline, or unavailable:

1. Open a shell in the Open WebUI container:
   - `docker exec -it <openwebui-container> sh`
2. Install the package manually:
   - Minimal pipe: `pip install "context-compiler>=0.6.14"`
   - Preprocessor pipe: `pip install "context-compiler[experimental]>=0.6.14"`
3. Import and enable the function in Open WebUI, then configure valves.

### Finding valid model ids

Use the Open WebUI model picker/list to copy exact model ids for `BASE_MODEL_ID`
(and optional `PREPROCESSOR_MODEL_ID` for the preprocessor pipe).

## Limitations

- No durable external persistence (checkpoint continuation is in-process only).
- No multi-worker or cross-process guarantees.
- No Redis/DB/external storage.
- No Filters or Pipelines.
- No production hardening.
- Version-coupled to Open WebUI internal helper/import paths.

## Manual Validation

Validate clarify short-circuit, passthrough forwarding without state injection,
update forwarding with compiler state (`[[cc_state]]`) added to the request, chat isolation
with real chat ids, restart state loss, and non-text bypass behavior.

Note: In the OpenWebUI example pipes, `update` decisions call the downstream
LLM with authoritative compiler state injected as a compiler-owned system
message (`[[cc_state]] ...`) for state-affecting updates. Administrative
updates (`clear state`, `clear premise`, `reset policies`, `remove policy <item>`)
return deterministic local acknowledgments and do not call the downstream LLM.
When trace is enabled, responses include concise evidence of decision kind,
active state, downstream LLM call/no-call, and whether state was injected.

## Behavioral comparisons

**Case 1**

- prompt(s): `clear state` → `change premise to formal tone`
- base model: “To adjust the tone… provide the original content…”
- basic pipe: `No premise exists yet. Use 'set premise ...' first.`
- preprocessor pipe: `No premise exists yet. Use 'set premise ...' first.`
- why this is a real win: lifecycle rule is enforced in a fixed, repeatable way; base model drifts into generic rewriting help.

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

- prompt(s): `clear state` → `set premise to concise replies`
- base model: accepts conversational style phrasing
- basic pipe: `Did you mean 'set premise concise replies'?`
- preprocessor pipe: same clarify (near-miss is not rewritten)
- why this is a real win: preprocessor stays reject-first and preserves engine-owned clarify behavior.

**Case 5**

- prompt(s): `clear state` → `change premise concise replies`
- base model: generic “please clarify changes” response
- basic pipe: `Did you mean 'change premise to concise replies'?`
- preprocessor pipe: same clarify (near-miss is passed through unchanged)
- why this is a real win: near-miss inputs are not canonicalized, so directive semantics stay engine-owned.
