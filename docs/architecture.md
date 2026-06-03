# Architecture Boundaries

Context Compiler is best understood as a deterministic conversational state
authority inside a larger host application stack.

## Acquisition Layer

Responsibilities:
- recognize possible user state updates before core compilation
- normalize candidate inputs conservatively
- abstain when intent is uncertain

Examples:
- the optional heuristic/LLM preprocessor
- host-side input shaping before `engine.step(...)`

Out of scope:
- authoritative state mutation
- final conflict resolution
- semantic classification as source of truth

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
- combine outputs from multiple authorities
- track provenance and resolve conflicts across authorities
- coordinate host behavior across multiple authorities

Examples:
- host-owned coordination that merges multiple state authorities
- provenance-aware conflict handling across authority outputs

Out of scope:
- current Context Compiler core behavior
- any implied built-in coordinator semantics today

The preprocessor belongs to the Acquisition Layer. It is optional,
conservative, and never the source of truth. Context Compiler core belongs to
the Authority Layer. Host applications own Application Layer behavior.
