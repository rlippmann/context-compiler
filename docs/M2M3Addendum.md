# Context Compiler — M2/M3 Constraint Addendum

*(Non-normative behavior specification; normative invariants only)*
This document defines architectural guarantees for future milestones.
It prevents incompatible future implementations while preserving design
freedom.
M1 remains the only fully normative behavioral specification.

## M2 — Scope & Session Control (Constraint Specification)

### Purpose

Introduce isolation boundaries so authoritative state applies only
within the intended conversational context.
M2 does **not** introduce inference, entity recognition correctness
guarantees, or semantic reasoning.

### Required Invariants

#### Scope Isolation

State in one scope MUST NOT influence another scope unless explicitly transferred.
Equivalent inputs in separate scopes produce identical decisions independent of prior scopes.

#### Clean Compilation

Compiled context MUST derive only from authoritative state, never from transcript reconstruction.
No implementation may reconstruct facts by scanning previous messages.

#### Explicit Reference Binding

References to prior subjects must resolve only if explicitly registered in the active scope.
Unresolved references MUST NOT guess or infer prior meaning.

#### Explicit Forgetfulness

Removal of state requires an explicit directive.Ending a scope implicitly removes all non-persistent state.

#### Preference Separation

Persistent user preferences and session-specific facts MUST be stored independently and applied deterministically.
Session reset MUST NOT alter persistent preferences.

#### Undefined Behavior (Deferred Decisions)

The following are intentionally unspecified:

- How scopes are detected or created
- Entity extraction algorithms
- UI/UX of topic switching
- Heuristics for implicit scope changes
- Naming or addressing of entities

Implementations may vary provided invariants hold.

## M3 — Cross-Session Recall (Constraint Specification)

### Milestone Purpose

Allow users to intentionally re-activate prior authoritative state without reintroducing contradictions or implicit history dependence.
M3 introduces persistence but does not introduce reasoning over history.

### M3 Required Invariants

#### Snapshot Authority

A snapshot is a complete authoritative state representation.Recalled snapshots MUST behave identically to live state.

#### Explicit Recall Only

Prior state MUST NOT affect current state unless recall is explicitly requested.
Passive memory is forbidden.

#### Replacement Semantics

Recalling a snapshot replaces active state entirely.No automatic merge is permitted.
Subsequent directives follow M1 update rules.

#### Temporal Safety

A recalled snapshot must not resurrect state that the user has explicitly cleared after the snapshot unless the recall explicitly targets that snapshot.

#### Selective Persistence

Users must be able to explicitly remove or pin stored snapshots.
Deletion prevents future recall but does not alter already active state.

#### M3 Undefined Behavior (Deferred Decisions)

- Snapshot storage medium
- Retention policy defaults
- Snapshot naming conventions
- Automatic snapshot triggers
- Snapshot summarization format
- Multi-snapshot selection UX

Implementations may vary provided invariants hold.

## Architectural Guarantee

Across all milestones:
Authoritative state is derived only from user directives and explicit recall operations.
The system must never infer, reconstruct, or learn state from model outputs or transcript history.

This addendum preserves interoperability across independent implementations while allowing experimentation in future milestones.
