# Context Compiler

Deterministic state management for LLM interactions

## Project Purpose

Modern LLM systems are powerful at reasoning but unreliable at
maintaining consistent state across interactions. Corrections compete
with prior statements instead of replacing them, topics bleed between
conversations, and long-term state accumulates contradictions rather
than resolving them.
This project introduces a deterministic state layer that governs
authoritative state independently of the model. The model performs
interpretation and generation, while the state engine manages deterministic authoritative state (premise and policies). By separating reasoning
from state authority, the system improves reliability without requiring
model retraining. The system never derives authoritative state from
model responses; only user directives modify state.
The goal is not to make the model smarter, but to make interactions
predictable: once a statement is corrected or scoped, future responses
must respect that change.

The engine is a deterministic state machine, not a semantic memory or
reasoning system.

## Architectural Principle

The state engine is authoritative and model-independent.
Model output is never interpreted to derive or modify state.
All state transitions originate from explicit user directives.

Behavioral details are authoritative in `docs/DirectiveGrammarSpec.md`.

## Project Milestones

### M1 — Deterministic State Engine (implemented)

**Goal**
Explicit user commitments persist reliably within a conversation.
A change directive means replacing previously set authoritative state, not evaluating conversational accuracy.

M1 established deterministic state transitions and explicit clarification behavior.
The current authoritative state shape and directive semantics are defined in `DirectiveGrammarSpec.md` (0.5 / schema version 2).

**Core capability:**

- Recognize explicit user directives that mutate premise or policies
- Apply explicit state changes as deterministic replacements
- Block ambiguous updates until clarified
- Maintain an authoritative state independent of prior messages
- Provide structured state for host-provided model context

**Deliverables:**

- Directive grammar (conservative pattern set)
- State data model (authoritative conversational state)
- Deterministic update rules for explicit directives and clarification
- Clarification mechanism for ambiguous mutations
- Context serialization interface (`export_json` / `import_json`, state → host application)
- Reference integration harness (example host)
- Tests: persistence and non-regression of deterministic state updates

**User-visible outcome:**

After correcting or constraining the assistant once, the behavior remains consistent for the rest of the conversation.

### M3 — Cross-Session Recall (implemented, engine-level / host-enabled)

**Goal**
Extend host-level workflows around persisted exported state safely and intentionally.

**Core capability:**

- Export current authoritative state
- Initialize a new engine from previously exported authoritative state
- Ensure restored authoritative state behaves identically to live state
- Support serialized continuation checkpoints for restoring both:
  - authoritative state
  - pending confirmation-required continuation state

**Deliverables:**

- Host-side storage/recovery patterns built on the existing import/export API
- Host-side storage/recovery patterns for checkpoint object/checkpoint JSON continuation restore

**User-visible outcome:**

Assistant remembers decisions across sessions without resurrecting contradictions.
Pending confirmation-required flows can be resumed when the host persists checkpoints.

`export_json()` / `import_json()` remain authoritative-state only.
Checkpoint APIs are separate and represent runtime continuation.
Long-term memory remains a host persistence responsibility, not an engine-owned store.

### 0.6.x

The 0.6.x line completed checkpoint support, precompiler boundary hardening, and
regression/conformance surfaces that prepare the project for the next milestone.

### 0.7 — Auditability & Boundary Hardening

**Goal**
Make engine behavior inspectable and externally controllable without guessing.

**Core capability:**

- State inspection
- Deterministic dry-run / preview
- Structural state diff
- Thin controller layer around step / preview / replay behavior
- Machine-readable REPL JSON output containing:
  - `decision`
  - `prompt_to_user`
  - `state`
- JSON input for initial state only:
  - `--initial-state-json`
  - `--initial-state-file`
- REPL LLM fallback as explicit optional mode:
  - `--with-llm-fallback`
  - requires `--with-precompiler`
  - never implicit
  - inspectable via preview / JSON output
- Explicit precompiler policy for multi-line, multi-sentence, and conversational-prefix input
  (for example `ok. prohibit peanuts`, `sure - use docker`, mixed conversational + directive content)
  that is rule-based, fixture-covered, and inspectable
- Define policy for directive-adjacent mixed-intent payloads
  (for example `use docker and explain why containers matter`),
  ensuring explicit, inspectable behavior without implicit interpretation

**Constraints:**

- No expansion of authoritative state model
- No implicit behavior
- No heuristic-heavy parsing
- Preserve separation between engine, precompiler, and host/controller layers

### Post-0.7 Direction

- Profile commands and workflow conveniences
- Additional tooling built on auditability surfaces
- Broader heuristic responsibility remains default-avoid unless tightly justified

### 1.0 Target

Conceptual completion is a stable minimal contract, not feature accumulation.

- Stable minimal engine contract
- Deterministic and inspectable behavior
- Strict compiler / precompiler / host separation
- No implicit behavior
- No authoritative state-model expansion
- Cross-language consistency with Python as source of truth
