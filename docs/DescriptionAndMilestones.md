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
interpretation and generation, while the state engine manages deterministic conversational state (facts and policies). By separating reasoning
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

## Project Milestones

### M1 — Deterministic State Engine (implemented)

**Goal**
Explicit user commitments persist reliably within a conversation.
A correction means replacing a previously set fact, not evaluating conversational accuracy.

In M1 the fact schema intentionally contains a single exclusive slot (`facts["focus.primary"]`).
This slot demonstrates deterministic fact replacement and correction semantics.

Policies (`policies.prohibit`) provide the primary mechanism for persistent conversational constraints.
Richer fact schemas may be introduced in future milestones.

**Core capability:**

- Recognize high-confidence user directives (facts and policies)
- Apply corrections as deterministic replacements
- Block ambiguous updates until clarified
- Maintain an authoritative state independent of prior messages
- Provide structured state for host-provided model context

**Deliverables:**

- Directive grammar (conservative pattern set)
- State data model (facts + policies)
- Deterministic update rules (exclusive vs additive slots)
- Clarification mechanism for ambiguous mutations
- Context serialization interface (`export_json` / `import_json`, state → host application)
- Reference integration harness (example host)
- Tests: persistence and non-regression of corrections

**User-visible outcome:**

After correcting or constraining the assistant once, the behavior remains consistent for the rest of the conversation.

### M3 — Cross-Session Recall

**Goal**
Extend host-level workflows around persisted exported state safely and intentionally.

**Core capability:**

- Export the current authoritative state
- Initialize a new engine from previously exported state
- Ensure restored state behaves identically to live state

**Deliverables:**

- Host-side storage/recovery patterns built on the existing import/export API

**User-visible outcome:**

Assistant remembers decisions across sessions without resurrecting contradictions.
