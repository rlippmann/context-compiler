# Architecture Boundaries

Context Compiler has three parts: a core engine that owns saved compiler state,
drafting code that prepares candidate directives, and application code that
uses that state at runtime.

## Core

The core engine stores the premise and policies, applies supported directives,
and exports or imports that state.

Repository: [`context-compiler`](https://github.com/rlippmann/context-compiler)

The core engine is the only part that changes saved compiler state. Raw input
enters through `engine.step(...)`; parsed `CanonicalDirective` values enter
through `engine.apply_directive(...)`.

## Drafting and normalization

Drafting code recognizes possible state updates, handles alternate phrasing,
and prepares candidate directives when needed. It can also abstain when intent
is uncertain.

Repository: [`context-compiler-directive-drafter`](https://github.com/rlippmann/context-compiler-directive-drafter)

Drafting remains outside the core and submits candidate directives through the
engine rather than changing compiler state directly.

## Application

Application code decides how saved compiler state affects runtime behavior. It
can use that state for prompt construction, tool gating, routing, retrieval,
schemas or configuration, and execution.

Repository: [`context-compiler-example-integrations`](https://github.com/rlippmann/context-compiler-example-integrations)
or a host application.

## Architectural Rationale: Flat Policy Independence

Policies are independent flat assertions. They do not include built-in:

- ordering;
- grouping;
- precedence;
- inheritance;
- synonym or antonym relationships;
- dependencies;
- hierarchy;
- domain ontology;
- interaction semantics.

This keeps state simple, portable, and easy to replay, while supporting
consistent behavior across language implementations. Relationship-heavy rules
can still live in drafting or application code instead of the core policy model.

## Architectural Rationale: Compose Instead of Expanding Core

Context Compiler intentionally does not own higher-level concerns such as policy
precedence, rule ordering, policy dependencies or composition, orchestration,
authorization and security policy, or domain-specific rule systems. Those
concerns may still be necessary, but Context Compiler does not define them
today. Where they belong, and what interface they require, should be driven by
concrete integrations.

Context Compiler can supply saved premise and policy state to those systems as
an input. Context Compiler answers, “What explicit state is currently active?”
Another policy, rules, orchestration, or security component can answer, “Given
that state, what should happen?”

This keeps the core small and avoids reinventing mature policy, rules,
orchestration, or authorization systems. Core currently does not define union,
intersection, merge, precedence, cross-engine conflict resolution, or policy
dependency and hierarchy rules. This is intentional: richer composition was
deferred until a real integration demonstrates the interface it needs, and
does not imply that those operations will be added to core. See
[Single Engine vs Multiple Engines](multi-engine.md) for the supported pattern.
