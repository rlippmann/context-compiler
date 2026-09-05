# Single Engine vs Multiple Engines

Most applications should start with a **single Context Compiler engine**.

A single engine is not a single rule.  
It maintains a complete saved state consisting of:

- one premise (a single explicit contextual or factual state)
- a set of per-item policy states (`use` or `prohibit`)

Because policies are keyed and independent, a single engine can represent many constraints simultaneously.

## What a Single Engine Handles

A single engine can manage:

- global constraints  
- conversational stance  
- explicit correction and replacement flows  
- policy removal and reset  
- authoritative-state persistence  

Example:

```text
User: set premise project deadline is Friday
User: prohibit docker
User: use uv
User: use pytest
```

All constraints coexist in a single deterministic state snapshot.

## Important Property

Policies do not interact with each other.

- There is no ordering  
- There is no grouping  
- There is no domain model  

Each policy entry is an independent key in state.

## When to Use Multiple Engines

Use multiple engines only when you need **independent state instances**, not additional expressiveness.

Typical cases:

- separate assistants or agents  
- separate user sessions  
- isolation between workflows  
- independent persistence or reset behavior  

## Combining Engines

Multiple engines keep their state and lifecycles separate. Core does not merge
engine state directly.

When a combined Context Compiler state is needed, application code should:

- provide directives it already has or constructs for replay;
- create a target engine;
- replay those directives into the target in the desired order;
- let the target engine’s normal directive and error behavior handle conflicts.

The source engines remain unchanged, and the target engine becomes the combined
state instance for that use.

Core does not currently define union, intersection, merge, precedence, or other
richer cross-engine composition behavior. These APIs were intentionally deferred
until concrete integrations demonstrate what behavior and interface are needed.

## Guideline

Start with one engine.

Introduce multiple engines only when you need **independent lifecycle or isolation**, not because a single engine is insufficient.
