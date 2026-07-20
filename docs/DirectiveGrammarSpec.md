# Context Compiler - Directive Grammar Specification (0.5)

## Goal

Provide deterministic, explicit, and model-independent conversational state updates.

This specification defines the authoritative state machine for canonical
directive handling.
It does not perform reasoning, inference, entity modeling,
natural-language understanding, or interpretation of assistant output.
Human-facing normalization, malformed-input recovery, and intent drafting are
outside the core canonical directive contract.

## 1. Terminology

| Term | Meaning |
| --- | --- |
| User Input | Raw text from the user |
| Directive | A string that matches one of the explicit grammar productions in Section 5 |
| Premise | Single sticky explicit slot controlled only by premise directives |
| Policy | Per-item authoritative state: `"use"` or `"prohibit"` |
| State | Current authoritative snapshot |
| Pending Clarification | A blocked canonical mutation awaiting explicit user confirmation |
| Decision | Compiler instruction returned to host |

## 2. System Responsibilities

The compiler:

1. Parses canonical user input against explicit grammar
2. Validates canonical directives and authoritative state
3. Applies deterministic state transitions only when valid
4. Returns `clarify` when a canonical operation cannot proceed under the core
   state rules
5. Returns a deterministic `Decision`

The compiler never calls an LLM.
All authoritative mutations originate from user directives passed to `step()`.

## 3. Host Responsibilities

The host:

- Displays clarification prompts
- Calls the LLM only when `Decision.kind` allows it
- Formats model context from compiler state
- May perform non-canonical input processing before core execution

## 4. Decision API Contract

```python
class Decision(TypedDict):
    kind: Literal["passthrough", "update", "clarify"]
    state: dict | None
    prompt_to_user: str | None
```

Semantics:

- `passthrough`: forward user input to LLM
- `update`: forward user input with updated compiler state
- `clarify`: do not call LLM; display `prompt_to_user`

The compiler always returns a `Decision`.

## 5. Engine/Host State Contract

This section defines the integration contract between the deterministic engine
and host applications. It is authoritative for engine behavior and host
integration code, not a requirement for user-facing UX presentation.

State is a deterministic snapshot:

```json
{
  "premise": null,
  "policies": {},
  "version": 2
}
```

Where:

- `premise`: `string | null`
- `policies`: `dict[string, "use" | "prohibit"]`
- `version`: integer schema version. The 0.5 design maps to schema version `2`.
- Policy key absence means no policy for that item.

UX note:

- User-facing surfaces (for example REPL or demos) may render this contract in
  human-readable form instead of exposing raw schema/JSON directly.

Properties:

- Premise is explicit and sticky.
- Policies are authoritative per item.
- No policy ordering.
- No policy recency semantics.
- No policy history semantics.

## 6. Normalization

`normalize_item(X)` for policy item keys:

1. Unicode NFKC normalization
2. Lowercase
3. Collapse internal whitespace to single spaces
4. Remove leading articles: `a`, `an`, `the`
5. Normalize apostrophes (`dont` -> `don't`)

Premise values are stored as opaque strings with minimal sanitation only:

1. Unicode normalization
2. Apostrophe normalization
3. Whitespace collapse

No stemming, synonym mapping, ontology, or semantic interpretation is allowed.

## 7. Directive Grammar (Explicit Only)

Only the exact productions below are canonical directives.
All other input is `passthrough` unless Section 8 says `clarify`.

```text
SET_PREMISE      := "set premise " VALUE
CHANGE_PREMISE   := "change premise to " VALUE
USE_ITEM         := "use " ITEM
PROHIBIT_ITEM    := "prohibit " ITEM
REMOVE_POLICY    := "remove policy " ITEM
REPLACE_USE      := "use " ITEM " instead of " ITEM
CLEAR_PREMISE    := "clear premise"
RESET_POLICIES   := "reset policies"
CLEAR_STATE      := "clear state"
```

Notes:

- `ITEM` is a non-empty raw substring after its prefix.
- One input may contain at most one canonical directive. If another canonical
  directive start appears later in the same input, the input is invalid under
  the current grammar and must return `clarify`.
- Recognized policy directives with empty or whitespace-only `ITEM` payload return `clarify`.
- Premise directive payload must contain at least one non-whitespace character after the prefix.
  Empty and whitespace-only premise payloads are invalid and must return `clarify`.
- `ITEM` is normalized via `normalize_item` before policy lookup/storage.
- `VALUE` is stored using premise sanitation from Section 6.
- Quote characters have no special parsing semantics. A fully quoted input remains ordinary `passthrough` unless the raw
  input begins with a canonical directive. Quote characters inside a
  recognized directive payload do not suppress later canonical directive
  detection.
- No conversational aliases are directives (for example: `actually`, `I meant`, `allow`, `you can`, `set X`, `I'm using X`).

## 8. State Transition Semantics

### 8.1 Premise lifecycle

- `set premise X`:
  - valid only if `state.premise is null`
  - if `X` is empty or whitespace-only after the prefix: `clarify` and no mutation
  - success: set `state.premise = sanitize_premise(X)`
  - if premise already exists: `clarify`

- `change premise to X`:
  - valid only if `state.premise is not null`
  - if `X` is empty or whitespace-only after the prefix: `clarify` and no mutation
  - success: replace premise with `sanitize_premise(X)`
  - if no premise exists: `clarify`

### 8.2 Policy lifecycle

Let `k = normalize_item(ITEM)`.

- `use ITEM`:
  - if `ITEM` payload is empty or whitespace-only after the prefix: `clarify` and no mutation
  - if `policies[k] == "prohibit"`: `clarify` (contradiction)
  - if `policies[k] == "use"`: no-op `update` (idempotent assertion)
  - else set `policies[k] = "use"`

- `prohibit ITEM`:
  - if `ITEM` payload is empty or whitespace-only after the prefix: `clarify` and no mutation
  - if `policies[k] == "use"`: `clarify` (contradiction)
  - if `policies[k] == "prohibit"`: no-op `update` (idempotent assertion)
  - else set `policies[k] = "prohibit"`

- `remove policy ITEM`:
  - if `ITEM` payload is empty or whitespace-only after the prefix: `clarify` and no mutation
  - remove `k = normalize_item(ITEM)` from `policies` if present
  - always return `update` (idempotent when absent)

### 8.3 Explicit replacement

Pending confirmation in core is limited to canonical operations that are
already fully determined by the submitted canonical directive. Core does not
use confirmation to repair non-canonical input, infer intent, or convert a
failed canonical operation into a different directive.

For `use X instead of Y`:

1. Let `kx = normalize_item(X)`, `ky = normalize_item(Y)`.
2. If `kx == ky`: no-op `update`.
3. Otherwise, evaluate in this exact order:
   - if `ky not in policies`: return ordinary `clarify` with prompt
     `"<Y>" is not currently in use.`
     `Replacement requires an active 'use' policy.`
   - else if `policies.get(ky) == "prohibit"`: return ordinary `clarify` with prompt
     `"Y" is currently prohibited.`
     `Submit explicit directive(s) to remove it or use a different item.`
   - else if `policies.get(kx) == "prohibit"`: return ordinary `clarify` with prompt
     `"X" is currently prohibited.`
     `Submit explicit directive(s) to remove it or use a different item.`
4. If none of the clarify conditions above match, `Y` must currently exist in
   policy state (`ky in policies`) or return `clarify`.
5. Replacement requires `policies[ky] == "use"` in the literal path; otherwise return `clarify`.
6. If replacement syntax is recognized but either side is empty/whitespace-only, return `clarify` and no mutation.
7. On literal success:
   - remove `ky` from `policies`
   - set `policies[kx] = "use"`

This operation is authoritative replacement, not recency resolution.

### 8.4 Administrative commands

- `clear premise`: set `premise = null` (cleared premise state)
- `reset policies`: set `policies = {}`
- `remove policy ITEM`: remove one normalized policy key from `policies` if present
- `clear state`: reset all authoritative state by setting `premise = null` and `policies = {}`

### 8.5 Compound directives

When no pending clarification exists, if an input begins with a canonical directive and a later canonical directive start also appears in the same input, the input is invalid under the current grammar.

Pending clarification handling in Section 10 takes precedence over compound-directive detection. While pending clarification exists, directive parsing is suspended and the input is processed only as a possible confirmation response.

Behavior:

- return `Decision.kind = "clarify"`
- do not mutate authoritative state
- do not create pending clarification or pending replacement state
- reuse the normal public clarify contract; there is no separate decision kind

Deterministic prompt:

`Multiple directives are not supported in one input.`
`Submit each directive separately.`

Examples:

- valid: `use docker`
- valid: `use docker instead of podman`
- invalid: `use docker and prohibit peanuts`
- invalid: `set premise vegetarian and use docker`
- invalid: `clear state then set premise new project`
- passthrough: `"use docker and prohibit peanuts"`
- invalid: `use "docker and prohibit peanuts"`
- invalid: `set premise "use docker and prohibit peanuts"`

## 9. Clarification Rules (Exhaustive)

The compiler returns `Decision.kind = "clarify"` only in these cases:

1. `set premise X` when a premise already exists.
2. `change premise to X` when no premise exists.
3. `set premise X` when `X` is empty or whitespace-only after the prefix.
4. `change premise to X` when `X` is empty or whitespace-only after the prefix.
5. `use ITEM` when that item is currently `"prohibit"`.
6. `prohibit ITEM` when that item is currently `"use"`.
7. `use X instead of Y` when `Y` does not exist in policies (`ky not in policies`).
8. `use X instead of Y` when `Y` is currently `"prohibit"`.
9. `use X instead of Y` when `X` is currently `"prohibit"`.
10. `use X instead of Y` when `Y` exists but is not `"use"` and no replacement-intent clarify rule applies.
11. A pending clarification exists and input is not an exact confirmation token.
12. `remove policy ITEM` when `ITEM` is empty or whitespace-only after the prefix.
13. `use ITEM` when `ITEM` is empty or whitespace-only after the prefix.
14. `prohibit ITEM` when `ITEM` is empty or whitespace-only after the prefix.
15. `use X instead of Y` when replacement syntax is recognized but `X` or `Y` is empty/whitespace-only.
16. When no pending clarification exists, an input contains more than one canonical directive start.

Contradictions never silently overwrite state.

### 9.1 Standardized clarify prompts

When `Decision.kind = "clarify"`, prompt text is deterministic only for the cases listed below.

- `set premise X` when premise already exists (Section 9 case 1):
  `Premise already set.`
  `Use 'change premise to <value>' to modify it.`
- `change premise to X` when no premise exists (Section 9 case 2):
  `No premise is set.`
  `Use 'set premise <value>' to define one.`
- `set premise X` with empty/whitespace-only payload (Section 9 case 3):
  `Premise value cannot be empty.`
  `Use 'set premise <value>' with a non-empty value.`
- `change premise to X` with empty/whitespace-only payload (Section 9 case 4):
  `Premise value cannot be empty.`
  `Use 'change premise to <value>' with a non-empty value.`
- `use ITEM` when that item is currently `"prohibit"` (Section 9 case 5):
  `"<item>" is currently prohibited.`
  `Remove or replace it before using it.`
- `prohibit ITEM` when that item is currently `"use"` (Section 9 case 6):
  `"<item>" is currently in use.`
  `Remove or replace it before prohibiting it.`
- `use X instead of Y` when `Y` does not exist in policies (Section 9 case 7):
  `"<Y>" is not currently in use.`
  `Replacement requires an active 'use' policy.`
- `use X instead of Y` when `Y` is currently `"prohibit"` (Section 9 case 8):
  `"Y" is currently prohibited.`
  `Submit explicit directive(s) to remove it or use a different item.`
- `use X instead of Y` when `X` is currently `"prohibit"` (Section 9 case 9):
  `"X" is currently prohibited.`
  `Submit explicit directive(s) to remove it or use a different item.`
- `use X instead of Y` when `Y` exists but is not `"use"` and no replacement-intent clarify rule applies (Section 9 case 10):
  `"<Y>" is not currently in use.`
  `Replacement requires an active 'use' policy.`
- Pending clarification unmatched input (Section 9 case 11):
  reuse the existing pending prompt unchanged.
- `remove policy ITEM` with empty/whitespace-only payload (Section 9 case 12):
  `Policy item cannot be empty.`
  `Use 'remove policy <item>' with a non-empty value.`
- `use ITEM` with empty/whitespace-only payload (Section 9 case 13):
  `Policy item cannot be empty.`
  `Use 'use <item>' with a non-empty value.`
- `prohibit ITEM` with empty/whitespace-only payload (Section 9 case 14):
  `Policy item cannot be empty.`
  `Use 'prohibit <item>' with a non-empty value.`
- Incomplete replacement payload (Section 9 case 15):
  `Replacement requires both new and old items.`
  `Use 'use <new item> instead of <old item>' with non-empty values.`
- Compound directive rejection when no pending clarification exists (Section 9 case 16):
  `Multiple directives are not supported in one input.`
  `Submit each directive separately.`

## 10. Pending Clarification

Normative eligibility rule:

- Pending confirmation is reserved for deterministic continuation of canonical
  operations already established by prior core decisions.
- Core must not use pending confirmation to authorize:
  - near-miss repair
  - malformed-input recovery
  - synthesized replacement directives
  - alternate human phrasing interpretation
  - semantic rewrites
  - materially different directives than the one originally submitted
- When an input needs non-canonical interpretation, core does not define that
  processing. Core operates only on canonical directives submitted to it.

Internal structure:

```python
pending = {
    "proposed_event": ...,
    "prompt": ...
}
```

While pending exists:

- Directive parsing is suspended.
- Only confirmation tokens are processed.
- Accepted affirmative tokens: `yes`, `yes please`, `yep`, `yeah`, `sure`, `ok`, `okay`
- Accepted negative tokens: `no`, `nope`, `no thanks`

Confirmation token normalization:

1. Trim surrounding whitespace
2. Lowercase
3. Collapse internal whitespace
4. Remove trailing punctuation: `. , ! ?`

Resolution:

- Affirmative token: apply pending event, clear pending, return `update`
- Negative token: discard pending event, clear pending, apply no mutation, return `update` with unchanged state
- Any other input: remain in `clarify`, no mutation, and keep the existing pending prompt

## 11. Context Serialization Contract

The compiler outputs structured state only; the host formats prompts.

Example:

```json
{
  "premise": "Use concise, formal language.",
  "policies": {
    "docker": "prohibit",
    "pytest": "use"
  },
  "version": 2
}
```

JSON persistence boundary:

- `engine.export_json()` serializes authoritative state.
- `engine.import_json(payload)` validates/canonicalizes payload and replaces active state.
- Policy keys are normalized during import validation/canonicalization.
- If a policy key normalizes to `""`, the payload is invalid and must be rejected.
- This aligns import-time state acceptance with directive-time behavior, where empty policy items are invalid.

Checkpoint boundary:

- `engine.export_checkpoint()` exports a checkpoint object contract.
- `engine.import_checkpoint(payload)` validates/restores a checkpoint object and returns `None`.
- `engine.export_checkpoint_json()` and `engine.import_checkpoint_json(payload)` are JSON string wrappers around the object form.
- Checkpoint includes both authoritative state and pending continuation state.

Checkpoint object contract:

```json
{
  "checkpoint_version": 1,
  "authoritative_state": {
    "premise": "Use concise, formal language.",
    "policies": {
      "docker": "prohibit",
      "pytest": "use"
    },
    "version": 2
  },
  "pending": null
}
```

Checkpoint semantics:

- `authoritative_state` uses the same validation/canonicalization boundary as `export_json` / `import_json`.
- `pending` captures confirmation-required continuation for supported canonical
  operations only.
- `pending` is `null` when there is no outstanding continuation.
- Restore is all-or-nothing: invalid checkpoint payloads raise and no partial state restore occurs.
- Continuation behavior is deterministic after restore (same confirmation token handling and resolution outcomes as live pending state).
- `checkpoint_version` is independent of authoritative state `version`; it must be bumped when checkpoint contract shape changes (especially `pending`).

## 12. Invariants

1. State changes only from valid canonical directive transitions or pending-confirmation acceptance for canonical operations.
2. Same input sequence yields identical state and decisions.
3. LLM output never mutates state.
4. No mutation occurs when returning `clarify`.
5. Premise updates are explicit and lifecycle-gated (`set` vs `change`).
6. Policy state is per-item authoritative (`"use" | "prohibit"`), never ordered/additive by history.
7. Contradictions always clarify; they never overwrite.
8. Premise can be explicitly cleared via `clear premise` (`premise = null`).
9. A single input never applies more than one canonical directive.
10. Core does not repair non-canonical human input into canonical directives.

## 13. Non-Goals

Not implemented:

- `has` / `have` parsing
- `is`-parsing
- entity modeling
- ordered policies
- dict+history hybrids
- natural-language understanding inside the compiler
- cross-session memory
- ontology reasoning
- agent planning
- output validation

Non-canonical input interpretation is intentionally excluded from core.

## End

Version 0.5 removes M1 recency and additive-policy semantics in favor of
explicit premise lifecycle and authoritative per-item policy state.
