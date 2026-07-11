# Architecture Boundaries

Context Compiler is best understood as a deterministic conversational state
authority inside a larger host application stack.

## Authority Layer

Responsibilities:
- apply deterministic state transitions
- enforce clarification and confirmation gates
- export/import authoritative state and checkpoints

Examples:
- Context Compiler core engine
- checkpoint continuation behavior

Repository:
- `context-compiler`

Boundary:
- only core applies directives
- only core mutates authoritative state

## Acquisition Layer

Responsibilities:
- recognize possible user state updates before core compilation
- normalize candidate inputs conservatively
- abstain when intent is uncertain
- draft candidate directives without becoming a second authority

Examples:
- external directive-drafter or host-owned drafting packages
- host-side input shaping before `engine.step(...)`

Repository:
- `context-compiler-directive-drafter`

Boundary:
- drafting is non-authoritative
- drafting must not bypass `engine.step(...)`
- drafting must not edit `engine.state`

## Application Layer

Responsibilities:
- decide how compiler state affects runtime behavior
- render prompts and acknowledgements
- select schemas, gate tools, route workflows, and apply runtime controls

Examples:
- runnable integrations owned outside core (for example
  `context-compiler-example-integrations` for OpenWebUI, LiteLLM, Ollama, or
  proxy/runtime/provider examples)
- host-controlled prompt construction from saved state

Repository:
- `context-compiler-example-integrations` or host applications

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

Relationship-heavy semantics may still be useful, but they generally belong in
drafting, orchestration, or domain-specific layers rather than in
the core authority model.
