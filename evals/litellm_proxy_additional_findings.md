# LiteLLM Proxy Additional Findings

Model: `ollama/qwen2.5:14b-instruct`

- Limitations/caveats:
  - Confirm follow-up (`yes`) does not resolve the prior confirm in current replay-only proxy flow.
  - Last-turn-only preprocessing can fail to persist earlier canonicalization effects across subsequent replay.
- Additional LiteLLM-surface behavior:
  - Structured mixed-content user payloads can trigger upstream LiteLLM/Ollama message-shape validation errors.
  - Structured text-part near-miss inputs still show a meaningful preprocessor lifecycle win over basic proxy.

## Finding 1 — confirm follow-up loops (replay limitation)

**Prompt sequence**
1. `clear state`
2. `use podman instead of docker`
3. `yes, keep existing policies and use podman`

**Vanilla**
- Step 2/3: generic Podman migration/help text.

**Basic proxy**
- Step 2: confirm clarify (`No exact policy found for "docker" ... Confirm to use "podman" ...`).
- Step 3: same confirm clarify repeats.

**Preprocessor proxy**
- Step 2: same confirm clarify.
- Step 3: same confirm clarify repeats.

**Why it matters**
Current replay-based proxy behavior does not treat natural-language “yes” as explicit confirm resolution, so this can loop until user supplies an explicit directive path.

## Finding 2 — last-turn-only preprocessing is non-persistent across replay (replay limitation)

**Prompt sequence**
1. `clear state`
2. `set premise to concise replies`
3. `Explain TCP in detail.`

**Vanilla**
- Conversationally accepts premise-like instruction, then gives normal long-form answer.

**Basic proxy**
- Step 2: syntax clarify (`Did you mean 'set premise concise replies'?`).
- Step 3: same syntax clarify repeats.

**Preprocessor proxy**
- Step 2: canonicalized update (`Premise set to concise replies ...`).
- Step 3: syntax clarify reappears (`Did you mean 'set premise concise replies'?`).

**Why it matters**
Only the latest replay turn is preprocessed; earlier raw near-miss text in transcript can still drive later replay outcomes.

## Finding 3 — structured mixed content can fail upstream validation (LiteLLM-surface caveat)

**Prompt sequence**
1. `clear state`
2. user content parts: text (`set premise to concise replies`) + non-text (`input_image`)
3. `What is TCP?`

**Vanilla**
- Upstream request fails with invalid user message shape error.

**Basic proxy**
- Blocks at compiler clarify before upstream model call.

**Preprocessor proxy**
- Step 2 hits upstream validation error path; later turn can return clarify.

**Why it matters**
In proxy mode, forwarded request messages remain unchanged; LiteLLM/Ollama payload validation behavior can dominate outcomes for mixed content shapes.

## Finding 4 — structured text-part near-miss still yields stronger lifecycle result (LiteLLM-surface win)

**Prompt sequence**
1. `clear state`
2. user content text parts: `change premise` + `concise replies`

**Vanilla**
- Conversational acceptance of style change.

**Basic proxy**
- Syntax clarify only (`Did you mean 'change premise to concise replies'?`).

**Preprocessor proxy**
- Lifecycle clarify (`No premise exists yet. Use 'set premise ...' first.`).

**Why it matters**
For structured text-part inputs, preprocessor canonicalization can move past syntax-only clarify and reach the stronger lifecycle-semantic outcome.
