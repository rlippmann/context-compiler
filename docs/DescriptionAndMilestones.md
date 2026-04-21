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

### M3 — Cross-Session Recall

**Goal**
Extend host-level workflows around persisted exported state safely and intentionally.

**Core capability:**

- Export the current authoritative state
- Initialize a new engine from previously exported state
- Ensure restored state behaves identically to live state
- Support serialized continuation checkpoints for restoring both authoritative state and pending confirmation-required continuation state

**Deliverables:**

- Host-side storage/recovery patterns built on the existing import/export API
- Host-side storage/recovery patterns for checkpoint object/JSON continuation restore

**User-visible outcome:**

Assistant remembers decisions across sessions without resurrecting contradictions.
