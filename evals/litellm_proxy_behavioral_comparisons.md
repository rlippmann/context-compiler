# LiteLLM Behavioral Comparison (5 documented directive/state cases)

Model: `ollama/qwen2.5:14b-instruct`

- Vanilla LiteLLM exhibits conversational drift on stateful directives.
- Basic proxy enforces deterministic state semantics.
- Preprocessor proxy additionally improves recall on near-miss inputs.

## Case 1 — premise lifecycle enforcement

**Prompt sequence**
1. `clear state`
2. `change premise to formal tone`

**Vanilla**
1. `State cleared. How can I assist you now?`
2. Generic rewriting guidance (asks for text/context to formalize).

**Basic proxy**
1. `State cleared. How can I assist you now?`
2. `No premise exists yet. Use 'set premise ...' first.`

**Preprocessor proxy**
1. `State cleared. How can I assist you now?`
2. `No premise exists yet. Use 'set premise ...' first.`

**Result / why it matters**
Both proxy modes enforce the premise lifecycle deterministically; vanilla drifts into conversational rewrite assistance.

## Case 2 — conflict enforcement

**Prompt sequence**
1. `clear state`
2. `use docker`
3. `prohibit docker`

**Vanilla**
1. `State cleared. How can I assist you now?`
2. Generic Docker tutorial.
3. Generic "stop/uninstall Docker" guidance.

**Basic proxy**
1. `State cleared. How can I assist you now?`
2. Generic Docker tutorial.
3. `'docker' is already in use. Only one policy per item is allowed. Use 'reset policies' to change it.`

**Preprocessor proxy**
1. `State cleared. How can I assist you now?`
2. Generic Docker tutorial.
3. `'docker' is already in use. Only one policy per item is allowed. Use 'reset policies' to change it.`

**Result / why it matters**
Both proxy modes preserve explicit conflict semantics instead of letting the model conversationally reinterpret contradictory instructions.

## Case 3 — replacement precondition enforcement

**Prompt sequence**
1. `clear state`
2. `use podman instead of docker`

**Vanilla**
1. `State cleared. How can I assist you now?`
2. Generic Podman migration tutorial.

**Basic proxy**
1. `State cleared. How can I assist you now?`
2. `No exact policy found for "docker". Replacement requires an exact policy match. Confirm to use "podman" and keep existing policies?`

**Preprocessor proxy**
1. `State cleared. How can I assist you now?`
2. `No exact policy found for "docker". Replacement requires an exact policy match. Confirm to use "podman" and keep existing policies?`

**Result / why it matters**
Both proxy modes enforce the replacement precondition (old item must exist), while vanilla skips that state-dependent requirement.

## Case 4 — near-miss canonicalization + premise slot semantics

**Prompt sequence**
1. `clear state`
2. `set premise to concise replies`
3. `set premise formal tone`

**Vanilla**
1. `State cleared. How can I assist you now?`
2. Accepts near-miss conversationally ("premise set to concise replies").
3. Accepts second set conversationally ("premise updated to formal tone").

**Basic proxy**
1. `State cleared. How can I assist you now?`
2. `Did you mean 'set premise concise replies'?`
3. `Did you mean 'set premise concise replies'?`

**Preprocessor proxy**
1. `State cleared. How can I assist you now?`
2. `Premise set to concise replies. What do you need help with?`
3. `Did you mean 'set premise concise replies'?`

**Result / why it matters**
Both proxy modes beat vanilla on deterministic grammar handling, but the preprocessor proxy goes further: it canonicalizes the near-miss at step 2 and reaches a real state update, while basic proxy stops at syntax clarify.

## Case 5 — near-miss upgrade to stronger lifecycle clarify

**Prompt sequence**
1. `clear state`
2. `change premise concise replies`

**Vanilla**
1. `State cleared. How can I assist you now?`
2. Conversational acceptance ("I will aim for more concise replies").

**Basic proxy**
1. `State cleared. How can I assist you now?`
2. `Did you mean 'change premise to concise replies'?`

**Preprocessor proxy**
1. `State cleared. How can I assist you now?`
2. `No premise exists yet. Use 'set premise ...' first.`

**Result / why it matters**
This is the clearest preprocessor-specific win: basic proxy stops at syntax clarify, while preprocessor canonicalizes and reaches the stronger lifecycle clarify outcome.
