
# Context Compiler

Deterministic conversational state for LLM systems.

Modern language models are strong at reasoning but unreliable at maintaining consistent state across interactions. Corrections compete with earlier statements, constraints disappear, and long conversations accumulate contradictions.

The **Context Compiler** introduces a deterministic state layer that governs authoritative conversational state independently of the model.

The model performs reasoning and generation.  
The compiler manages facts and constraints.

Once a directive is accepted, it becomes authoritative for the remainder of the session.

---

## 10-Second Example

User sets a constraint once:

```text
User: don't use docker
```

State becomes:

```json
{
  "facts": {
    "focus.primary": null
  },
  "policies": {
    "prohibit": ["docker"]
  },
  "version": 1
}
```

Later in the conversation:

```text
User: how should I deploy my service?
```

The host supplies the compiled state to the model so the constraint persists across turns.

---

## Why Not Just Prompt Engineering?

Prompt instructions are soft and easy to lose across long interactions.

The Context Compiler gives the host an **authoritative state snapshot** that is independent of transcript drift.

Only **explicit user directives** can modify state.

In other words:

- the model reasons
- the compiler decides whether state changes
- the host controls when the LLM runs

---

## Architecture

```text
User Input
   ↓
Context Compiler
   ↓
Decision (passthrough | update | clarify)
   ↓
Host Application
   ↓
LLM
```

The compiler governs conversational state.  It never calls the LLM.

The LLM performs reasoning and generation but cannot modify authoritative state.

The host application decides whether the model runs based on the compiler’s `Decision`.

### Compiler responsibilities

The compiler:

1. Parses user input
2. Detects explicit directives
3. Ensures mutations are unambiguous
4. Returns a deterministic `Decision`

The compiler **never calls the LLM**.

### Host responsibilities

The host:

- displays clarification prompts
- calls the LLM when allowed
- formats prompts using compiled state

---

## Decision API

Each user message produces a `Decision`.

```python
class Decision(TypedDict):
    kind: Literal["passthrough", "update", "clarify"]
    state: dict | None
    prompt_to_user: str | None
```

Meaning:

| kind        | host behavior                                 |
|-------------|-----------------------------------------------|
| passthrough | forward user input to LLM                     |
| update      | forward input with updated state              |
| clarify     | show `prompt_to_user` and do not call the LLM |

---

## State Model

The compiler maintains an authoritative state snapshot:

```json
{
  "facts": {
    "focus.primary": null
  },
  "policies": {
    "prohibit": []
  },
  "version": 1
}
```

**Note**
In M1, the fact schema contains a single exclusive slot: `facts["focus.primary"]`.

This slot exists to demonstrate deterministic fact replacement and correction semantics.
Richer fact schemas may be introduced in future milestones.

### State Properties

- **Facts are exclusive** (last write wins)
- **Policies are additive**
- **No inference or semantic reasoning**
- **State is deterministic**

The same input sequence always produces the same state.

---

## Directive Examples

Hard negative directive:

```text
User: don't use docker
```

Result:

```json
{
  "policies": {
    "prohibit": ["docker"]
  }
}
```

Fact configuration:

```text
User: I'm using MacBook M3
```

State update:

```text
facts.focus.primary = "MacBook M3"
```

Correction:

```text
User: actually MacBook M2
```

Result:

```text
facts.focus.primary = "MacBook M2"
```

Ambiguous mutation:

```text
User: no use docker
```

Compiler response:

```text
Decision.kind = "clarify"
```

No state mutation occurs until confirmation.

## Reset Commands

Two explicit reset commands are supported:

- `reset policies` clears `policies.prohibit` but preserves the current fact (`facts["focus.primary"]`)
- `clear state` resets the full state to initial values

Example:

Before:

```json
{
  "facts": {"focus.primary": "oracle"},
  "policies": {"prohibit": ["stored procedures"]},
  "version": 1
}
```

After `reset policies`:

```json
{
  "facts": {"focus.primary": "oracle"},
  "policies": {"prohibit": []},
  "version": 1
}
```

After `clear state`:

```json
{
  "facts": {"focus.primary": null},
  "policies": {"prohibit": []},
  "version": 1
}
```

---

## Examples

The `examples/` directory contains small integration demonstrations.

- [Persistent guardrails](examples/01_persistent_guardrails.py)  
  Demonstrates constraints persisting across turns.

- [Configuration with correction](examples/02_configuration_and_correction.py)  
  Shows deterministic fact replacement.

- [Ambiguity detection with clarification](examples/03_ambiguity_with_clarification.py)  
  Demonstrates clarification before state mutation.

- [Tool governance for agents](examples/04_tool_governance_denylist.py)  
  Shows how host applications can block tools using compiler policies.

- [LLM integration pattern](examples/05_llm_integration_pattern.py)  
  Demonstrates the host control flow around the `Decision` API.

---

## Quickstart

Run the interactive REPL:

```bash
context-compiler
```

Run an example:

```bash
python examples/01_persistent_guardrails.py
```

Run tests:

```bash
pytest
```

---

## Guarantees

The compiler enforces several invariants:

- State never changes without explicit directive or confirmation
- The same input sequence always produces the same state
- LLM output never affects state
- No mutation occurs during clarification
- Facts are exclusive
- Policies are additive
- Pending clarification blocks mutation

---

## Current Milestone

The current implementation corresponds to:

### M1 — Deterministic State Engine

Goal:

Ensure explicit user corrections and constraints persist reliably within a single conversation.

---

## Future Milestones

Only **M1** is currently implemented.

Possible future work:

### M2 — Scope & Session Control (optional)

Introduce isolation boundaries so state applies only within the intended conversational context.

### M3 — Cross-Session Recall

Allow explicit recall of prior authoritative state across sessions.

### M4 — MCP Integration (optional)

Expose the state engine through a standardized context interface.

### M5 — Branch Awareness (optional / experimental)

Provide tools for managing multiple conversation branches during exploratory discussions.

---

## Design Philosophy

The Context Compiler deliberately avoids:

- semantic reasoning
- ontology inference
- machine-learning parsing
- transcript reconstruction
- passive memory

Authoritative state must originate only from **explicit user directives**.

---

## Specification

The authoritative behavioral specification is:

```text
M1Design.md
```

Future milestone documents describe potential extensions but are not normative for current behavior.

---

## License

Apache-2.0.
