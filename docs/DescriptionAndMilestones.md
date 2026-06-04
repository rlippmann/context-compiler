# Context Compiler

Reliable state handling for LLM conversations

## Project Purpose

LLM systems are strong at reasoning, but they can lose consistency across turns.
Corrections may compete with earlier instructions, topics can leak between
conversations, and state can conflict over time.
This project adds a deterministic state layer that is independent of the model.
The model handles interpretation and generation; the engine handles premise and
policies. Only explicit user directives can change state.
When the model reasons and the engine owns state, behavior stays reliable
without retraining the model. The system never derives authoritative state from
model responses.
The goal is not to make the model smarter, but to make interactions
predictable: once a statement is corrected or scoped, future responses
must respect that change.

The engine is a deterministic state machine. It is not a memory or
reasoning layer.

## Architectural Principle

The state engine is the source of truth and is model-independent.
Model output is never interpreted to derive or modify state.
All state transitions originate from explicit user directives.

Context Compiler remains deterministic conversational state authority.

Behavioral details are defined in `docs/DirectiveGrammarSpec.md`.

## Project Milestones

### M1 — Deterministic State Engine (implemented)

**Goal**
Explicit user commitments persist reliably within a conversation.
A change directive replaces previously set state. It does not judge whether earlier conversation content was "correct."

M1 established deterministic state transitions and explicit clarification behavior.
The current authoritative state shape and directive semantics are defined in `DirectiveGrammarSpec.md` (0.5 / schema version 2).

**Core capability:**

- Recognize explicit user directives that mutate premise or policies
- Apply explicit state changes as deterministic replacements
- Block ambiguous updates until clarified
- Maintain a source-of-truth state that does not depend on prior model wording
- Provide structured state for app-provided model context

**Deliverables:**

- Directive grammar (conservative pattern set)
- State data model (authoritative conversational state)
- Deterministic update rules for explicit directives and clarification
- Clarification mechanism for ambiguous mutations
- Context serialization interface (`export_json` / `import_json`, state → app layer)
- Reference integration harness (example host)
- Tests: persistence and non-regression of deterministic state updates

**User-visible outcome:**

After correcting or constraining the assistant once, the behavior remains consistent for the rest of the conversation.

### M3 — Cross-Session Recall (implemented, engine-level / host-enabled)

**Goal**
Help apps safely reuse saved exported state.

**Core capability:**

- Export current authoritative state
- Initialize a new engine from previously exported authoritative state
- Ensure restored authoritative state behaves identically to live state
- Support serialized continuation checkpoints for restoring both:
  - authoritative state
  - pending confirmation-required continuation state

**Deliverables:**

- App-side storage and recovery patterns built on the existing import/export API
- App-side storage and recovery patterns for checkpoint object and checkpoint JSON restore

**User-visible outcome:**

When apps persist exported state, assistants can carry decisions across sessions without reintroducing old conflicts.
Pending confirmation-required flows can be resumed when the app persists checkpoints.

`export_json()` / `import_json()` remain authoritative-state only.
Checkpoint APIs are separate and represent runtime continuation.
Long-term memory remains an app persistence responsibility, not an engine-owned store.

### 0.6.x

The 0.6.x line completed checkpoint support, preprocessor boundary hardening, and
regression/conformance surfaces that prepare the project for the next milestone.

### 0.7 — Auditability & Boundary Hardening

**Goal**
Make engine behavior inspectable and externally controllable without guessing.

**Core capability:**

- State inspection
- Deterministic dry-run / preview
- Structural state diff
- Thin stateless controller layer around step / preview behavior
- Machine-readable REPL JSON output containing:
  - versioned one-object-per-line output (`output_version`)
  - step / preview / state command result envelopes
- JSON preload for authoritative state and checkpoint continuation:
  - `--initial-state-json`
  - `--initial-state-file`
  - `--initial-checkpoint-json`
  - `--initial-checkpoint-file`
- Explicit preprocessor policy for multi-line, multi-sentence, and conversational-prefix input
  (for example `ok. prohibit peanuts`, `sure - use docker`, mixed conversational + directive content)
  that is rule-based, fixture-covered, and inspectable
- Define policy for directive-adjacent mixed-intent payloads
  (for example `use docker and explain why containers matter`),
  ensuring explicit, inspectable behavior without implicit interpretation

**Constraints:**

- No expansion of authoritative state model
- No implicit behavior
- No heuristic-heavy parsing
- Preserve separation between engine, preprocessor, and host/controller layers

### 0.8 — Architectural Decomposition (approved direction)

The approved 0.8 direction is to document and preserve the architectural
decomposition that has emerged around the current engine and experimental
preprocessor work. Behavior is expected to be preserved initially rather than
redesigned.

#### Authority Layer

Context Compiler core remains the Authority Layer and continues to serve as
deterministic conversational state authority.

Responsibilities:

- deterministic state transitions
- contradiction handling
- clarification handling
- pending confirmation flows
- checkpoints
- preview/diff
- authoritative state ownership

The Authority Layer remains the only layer that applies directives and the only
layer that mutates authoritative state.

#### Acquisition Layer

The current experimental preprocessor direction belongs to the Acquisition
Layer.

Planned 0.8 extraction target:
`context-compiler-directive-drafter`

Responsibilities:

- directive-adjacent interpretation
- conservative natural-language-to-directive drafting
- candidate directive generation
- possible future suggestion/proposal workflows outside the initial 0.8 extraction scope

Important boundary:

- drafts are non-authoritative
- drafting proposes
- authority decides
- only core applies directives
- only core mutates authoritative state

The Directive Drafter may draft candidate directive strings.

It must not:

- mutate authoritative state
- bypass `engine.step(...)`
- edit `engine.state`
- become a second authority

0.8 direction:

> Extraction of the experimental preprocessor into a separate package:
>
> `context-compiler-directive-drafter`

The initial goal is extraction with preserved behavior, not API redesign.

#### Composition Layer

The Composition Layer is a future possibility only and is not planned for 0.8.

Examples:

- multiple authorities
- profiles
- domain-specific authorities
- provenance
- conflict resolution
- effective-state computation

### 0.9 Candidate Direction — Canonical Export Integrity / Hashing

This is future planning only. No 0.9 implementation is defined here.

Candidate goals:

- canonical serialization
- deterministic hashes of exported artifacts
- Python/TypeScript verification
- auditability
- future signing compatibility

Explicitly out of scope:

- signing
- key management
- trust infrastructure
- security guarantees from hashes alone
- hashes embedded inside semantic engine state

### Post-0.8 Direction

- 0.9 candidate direction: canonical export integrity and hashing
- MCP adapter likely as a separate/later track after 0.8 extraction direction is clearer
- Optional MCP-readiness helpers only if narrowly justified
- Additional tooling built on auditability surfaces

### 1.0 Target

Conceptual completion is a stable minimal contract, not feature accumulation.

- Stable minimal engine contract
- Deterministic and inspectable behavior
- Strict compiler / preprocessor / host separation
- No implicit behavior
- No authoritative state-model expansion
- Cross-language consistency with Python as source of truth
