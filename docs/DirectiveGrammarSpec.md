# Context Compiler — Directive Grammar Specification

## Goal

Ensure explicit user corrections and constraints persist reliably within
a single conversation.
This specification provides authoritative conversational state. It does **not** perform
reasoning, inference, entity resolution, cross-session memory, or
planning.

### 1. Terminology

|            |                                                                |
|------------|----------------------------------------------------------------|
| Term       | Meaning                                                        |
| User Input | Raw text from the user                                         |
| Directive  | A statement attempting to change authoritative state           |
| Policy     | A standing constraint (“don’t do X”)                           |
| Fact       | A configuration choice about the current focus (“I’m using X”) |
| State      | Current authoritative truth snapshot                           |
| Pending    | Awaiting clarification before mutation                         |
| Decision   | Compiler instruction returned to host                          |

### 2. System Responsibilities

Compiler Responsibilities

The compiler:

1. Parses user input
2. Determines if state changes
3. Ensures mutations are unambiguous
4. Returns a deterministic `Decision`

The compiler never calls the LLM.
Mutations are expressed through directive input to `step()`, including reset/clear operations.
Imperative convenience methods such as `reset_policies()` and `clear_state()` are not part of the public API.

### 3. Host Responsibilities

The host:

- Displays clarification prompts
- Calls the LLM when allowed
- Formats prompts using provided state
- May read state snapshots directly, but should prefer public helper accessors where available.

Current helpers:
- `get_focus_value(state)`
- `get_prohibited_items(state)`

These helpers are read-only conveniences for state snapshots to reduce direct
coupling to nested layout. They do not modify compiler state and are not
semantic/compiler primitives.

### 4. Decision API Contract

`python
    class Decision(TypedDict):
        kind: Literal["passthrough", "update", "clarify"]
        state: dict | None
        prompt_to_user: str | None
`

#### Semantics

|             |                                       |
|-------------|---------------------------------------|
| kind        | Host behavior                         |
| passthrough | forward user input to LLM             |
| update      | forward user input with updated state |
| clarify     | DO NOT call LLM; show prompt_to_user  |

The compiler always returns a `Decision`.

### 4. State Model

State is a deterministic snapshot:
`json
    {
      "facts": {
        "focus.primary": null
      },
      "policies": {
        "prohibit": []
      },
      "version": 1
    }
`

#### Properties

- Keys are explicit
- Values are opaque strings
- Facts are exclusive (last write wins)
- Policies are additive sets
- No reasoning or inference occurs

### 5. Directive Parsing Rules

The compiler mutates state only on high-confidence directives.

#### 5.1 Hard Negative Directives

Accepted patterns:

- "don't X"
- "do not X"
- "never X"
- "please don't X"

Produces:

    POLICY_ADD(normalize(X))

For hard-negative directives, `normalize(X)` is applied to each policy
payload item before storage.

Soft preference phrases like `"avoid X"` and `"refrain from X"` are
not hard directives in M1. They are treated as passthrough input and do
not mutate authoritative state.

#### 5.2 Hard Positive Directives

Accepted patterns:

- "use X"
- "set X"
- "I am using X"
- "I'm using X"

Polite prefixes such as `"please"` may be tolerated and ignored by the parser.
For example, `please use X` is treated the same as `use X`.

Produces:

    FACT_SET(key="focus.primary", value=X)

“Using” statements set the current discussion focus, not inventory.
Hard-positive directives store fact values as opaque strings and do not
apply `normalize(X)` to the stored fact value.

#### 5.3 Correction Markers

Accepted markers:

- "actually"
- "I meant"
- "correction:"
- "no,"

Corrections apply only to the most recently updated exclusive
fact. If no such fact exists → clarification required.
Correction payloads must represent a fact replacement value. If a
correction payload appears to invoke another directive family (for
example hard-negative directives, allow/removal directives, or
reset/clear commands) → clarification required and no state mutation.

Example:

    use Nord Stage 4
    actually don't use docker

→ `Decision.kind = "clarify"` and state remains unchanged.

#### 5.4 Allow / Removal Directives

Accepted patterns:

- "X is fine"
- "allow X"
- "you can X"

Produces:

    POLICY_REMOVE(normalize(X))

If X not present → no-op.
For allow/removal directives, `normalize(X)` is applied to each policy
payload item used for removal matching.

#### 5.5 List Handling

For additive predicates:

- Split on commas and “and”
- Apply normalization to each item

For exclusive predicates:

- Multiple values → clarification

### 6. Normalization

`normalize(X)` performs:

1. Unicode NFKC normalization
2. Lowercase
3. Collapse whitespace
4. Remove leading articles: a, an, the
5. Normalize apostrophes (`dont` → `don't`)

No stemming, synonym mapping, ontology, or semantic interpretation.

Policy payloads (add/remove) use `normalize(X)` exactly as defined above.

Fact values do not use `normalize(X)`. They may receive minimal input
sanitation only:

1. Unicode normalization
2. Apostrophe normalization
3. Whitespace collapse

Fact sanitation does not include lowercasing or leading-article removal.

### 7. Ambiguity Handling

If a message might mutate state but is unclear:

    Decision.kind = "clarify"
    Decision.prompt_to_user = clarification question

This includes correction payloads that appear to invoke another
directive family.

Examples:

- "don use parallel octaves"
- "no use docker"

No state mutation occurs.

Non-directive input is always treated as passthrough; the compiler does not evaluate usefulness.

### 8. Pending Clarification

Internal structure:
`python
    pending = {
        proposed_event
    }
`

Resolution:

|              |               |
|--------------|---------------|
| **Response** | Action        |
| affirmative confirmation token | apply event   |
| negative confirmation token    | discard event |

Confirmation parsing takes precedence over all other directive parsing
while pending clarification exists.

A pending clarification resolves only when normalized user input exactly
matches one of the confirmation tokens.

Normalization for pending confirmation matching:

1. Trim surrounding whitespace
2. Lowercase
3. Collapse internal whitespace to single spaces
4. Remove trailing punctuation: `. , ! ?`

Accepted affirmative confirmation tokens:

- `yes`
- `yes please`
- `yep`
- `yeah`
- `sure`
- `ok`
- `okay`

Accepted negative confirmation tokens:

- `no`
- `nope`
- `no thanks`

If no pending exists → confirmation tokens are passthrough.
If normalized input does not match a confirmation token while pending
exists, the compiler remains in clarify, does not trigger other
directive parsing, and does not mutate state.

### 9. State Update Semantics

#### Facts (exclusive)

    focus.primary = "nord stage 3"
    focus.primary = "nord stage 4"

→` only stage 4 active`

#### Policies (additive)

    don't use parallel octaves
    do not use voice crossing

Adding duplicate policy is a no-op.
Policies stored in sorted lexical order.

Administrative state initialization/replacement is supported through:
- constructor input (`create_engine(state=...)` / `Engine(state=...)`) for initial load
- `engine.import_json(payload)` (JSON replacement)

Import-based replacement clears pending clarification state and must behave like
live state for subsequent `step()` calls.

### 10. Context Serialization Contract

The compiler outputs structured state only. The host formats prompts.

Example:

`json
    {
      "facts": {"focus.primary": "nord stage 4"},
      "policies": {"prohibit": ["parallel octaves"]}
    }
`

JSON persistence boundary:
- `engine.export_json()` serializes authoritative state for transport/storage.
- `engine.import_json(payload)` validates/canonicalizes payload and fully replaces active state.

### 11. Reset Commands

Explicit only:

- "reset policies"
- "clear state"

Produces:

    if command == "reset policies":
        state.policies.prohibit = []
    elif command == "clear state":
        state = initial_state
    Decision.kind = "update"

### 12. Non-Goals

Not implemented:

- reference resolution
- cross-session memory
- logical contradiction detection
- ontology reasoning (Docker Ë container)
- scoped overrides
- output validation
- agent planning

### 13. Invariants

1. State never changes without high-confidence directive or confirmation
2. Same input sequence → identical state
3. LLM output never affects state
4. No mutation occurs during `clarify`
5. Facts are exclusive; policies are additive
6. Pending clarification blocks mutation

### 14. Property Tests (Required)

Examples:

**Determinism** Same sequence → same state
**Safety** Near-miss input never mutates state
**Replacement** Later fact overwrites earlier fact
**Persistence** Policies persist across turns
**Idempotency** Duplicate policy adds do nothing

## End

This milestone establishes the authoritative truth layer.All later
milestones build on this deterministic contract.
