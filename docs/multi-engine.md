# Single Engine vs Multiple Engines

Most applications should start with a **single Context Compiler engine**.

A single engine is not a single rule.  
It maintains a complete saved state consisting of:

- one premise (a single explicit conversational stance)
- a set of per-item policy states (`use` or `prohibit`)

Because policies are keyed and independent, a single engine can represent many constraints simultaneously.

## What a Single Engine Handles

A single engine can manage:

- global constraints  
- conversational stance  
- explicit correction and replacement flows  
- policy removal and reset  
- transcript replay and persistence  

Example:

```text
User: set premise concise, practical answers
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

## Composition Is an App Concern

The compiler does not coordinate multiple engines.

The app is responsible for:

- selecting which engine(s) apply  
- combining state into model context  
- managing lifecycle (reset, persistence, replay) per engine  

The compiler only maintains a single state instance per engine.

## Guideline

Start with one engine.

Introduce multiple engines only when you need **independent lifecycle or isolation**, not because a single engine is insufficient.

## Combining Policies from Multiple Sources

If you need to combine constraints from separate sources, do it explicitly in
host code: replay directives through `step(...)` into a target engine.

Pattern:

1. Select ordered source directives
2. Replay each directive via `engine.step(...)`
3. Handle any returned `clarify` decisions explicitly

This keeps conflict handling in normal engine behavior and avoids adding merge
rules to core state APIs.
