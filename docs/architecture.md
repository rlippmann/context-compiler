# Architecture Boundaries

Context Compiler is best understood as a deterministic conversational state
authority inside a larger host application stack.

## Acquisition Layer

Responsibilities:
- recognize possible user state updates before core compilation
- normalize candidate inputs conservatively
- abstain when intent is uncertain
- draft candidate directives without becoming a second authority

Examples:
- external directive-drafter or host-owned drafting packages
- host-side input shaping before `engine.step(...)`

Out of scope:
- authoritative state mutation
- final conflict resolution
- semantic classification as source of truth
- bypassing `engine.step(...)`
- editing `engine.state`

## Authority Layer

Responsibilities:
- apply deterministic state transitions
- enforce clarification and confirmation gates
- export/import authoritative state and checkpoints

Examples:
- Context Compiler core engine
- transcript replay
- checkpoint continuation behavior

Out of scope:
- prompt rendering
- tool selection
- moderation or policy classification
- non-authoritative drafting or proposal UX

## Application Layer

Responsibilities:
- decide how compiler state affects runtime behavior
- render prompts and acknowledgements
- select schemas, gate tools, route workflows, and apply runtime controls

Examples:
- Open WebUI, LiteLLM, and Ollama structured-output integrations
- host-controlled prompt construction from saved state

Out of scope:
- changing compiler semantics
- inferring new state without explicit directives

## Classification Layer

Responsibilities:
- safety, moderation, semantic intent detection, and ontology/classification work
- external policy analysis before or around model calls

Examples:
- moderation systems
- safety classifiers
- semantic routing/classification services

Out of scope:
- deterministic compiler state transitions
- checkpoint and clarification authority

## Composition Layer

Responsibilities:
- coordinate multiple authority instances when a host uses them
- decide which authority outputs apply to a request

Examples:
- separate project contexts
- separate user profiles
- independent authority instances

Out of scope:
- current Context Compiler core behavior
- built-in coordination behavior

Acquisition-layer drafting belongs outside Context Compiler core. Context
Compiler core belongs to the Authority Layer. Host applications own
Application Layer behavior.

Composition remains exploratory. It is a future possibility, not a planned 0.8
core change.

## Architectural Rationale: Flat Policy Independence

Policies are intentionally modeled as independent flat assertions.

The model intentionally does not include:

- ordering
- grouping
- precedence
- inheritance
- synonym relationships
- antonym relationships
- dependencies
- hierarchy
- ontology-style reasoning
- interaction semantics

This is a deliberate architectural boundary, not an omitted convenience
feature.

Policy independence is a major contributor to:

- determinism
- portability
- replay consistency
- checkpoint stability
- cross-language conformance

Because policies are independent flat assertions, directive semantics stay
simple, exported state stays portable, replay remains exact, and checkpoint
continuation does not depend on hidden relational logic.

Changing this model would be a major architectural change with consequences
for:

- directive semantics
- fixtures
- replay
- checkpoints
- language parity
- future composition systems

Relationship-heavy semantics may still be useful, but they generally belong in
drafting, orchestration, composition, or domain-specific layers rather than in
the core authority model.
