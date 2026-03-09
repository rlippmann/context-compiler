# Context Compiler

Deterministic state management for LLM interactions\

## Project Purpose

Modern LLM systems are powerful at reasoning but unreliable at
maintaining consistent state across interactions. Corrections compete
with prior statements instead of replacing them, topics bleed between
conversations, and long-term state accumulates contradictions rather
than resolving them.
This project introduces a deterministic state layer that governs
authoritative state independently of the model. The model performs
interpretation and generation, while the state engine manages facts and
policy additions/removals, scope, and recall. By separating reasoning
from state authority, the system improves reliability without requiring
model retraining. The system never derives authoritative state from
model responses; only user directives modify state
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

### M1 — Deterministic State Engine

**Goal:**

Explicit user commitments persist reliably within a conversation.
A correction means replacing a previously set fact, not evaluating conversational accuracy.

In M1 the fact schema intentionally contains a single exclusive slot (`facts["focus.device"]`).
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

- Context serialization interface (state → host application)

- Reference integration harness (example host)

- Tests: persistence and non-regression of corrections

**User-visible outcome:**

After correcting or constraining the assistant once, the behavior remains consistent for the rest of the conversation.

### M2 — Scope & Session Control (optional)

**Goal:**

Prevent topic leakage and cross-contamination between conversations.

**Core capability:**

- Session scopes

- Explicit referent registration and binding

- Controlled entity allow/block lists (“forget X”)

- Clean-room context compilation

- Separate profile preferences from session state

**Deliverables:**

- Scope lifecycle model

- Deterministic reference binding and scoped state isolation

- Scope reset logic

- Context filtering layer

- Tests: no topic bleed; preferences persist

**User-visible outcome:**

New topic feels clean; old projects do not resurface unintentionally.

### M3 — Cross-Session Recall**

**Goal**
Recall past sessions safely and intentionally.

**Core capability:**

- Persist authoritative state when a session closes

- Restore prior state into the active session only through an explicit
  recall operation

- Recalling a snapshot replaces the active state; subsequent user
  directives may modify it

- Allow selective forgetting and pinning of stored snapshots

- Ensure recalled state behaves identically to live state

**Deliverables:**

- Snapshot storage

- Recall API

- Forget/pin controls

- Optional session summary generator

- Tests: recall respects refutations and bans

**User-visible outcome:**

Assistant remembers decisions across sessions without resurrecting contradictions.

### M4 — MCP Integration (optional)

**Goal**
Expose the state engine via a standardized context interface.

**Core capability:**

- Read state (active facts, policies, constraints, scope)

- Write events (correction, forget entity, close scope)

- Interoperable with model ecosystems

**Deliverables:**

- MCP provider implementation

- Read/write context endpoints

- Documentation for integration

**User-visible outcome:**

System can plug into external agents and tools
without custom adapters.

### M5 — Branch Awareness (Optional / Advanced)

**Goal**
Make long exploratory conversations navigable.

**Core capability:**

- Detect multiple discussion threads

- Branch registry

- Conversation map

- Anchor selection

**Deliverables:**

- Branch data model

- Drift detection logic

- Map generation

- Tests: branch isolation and restoration

**User-visible outcome:**

Brainstorming stays structured and resumable.

## Milestone Relationships

M1 is the foundation.

M3 builds directly on M1 and may be implemented without M2.

M2 introduces optional scope and session isolation.

M4 is an optional integration milestone.

M5 is optional and independent of the other milestones.
