
# Context Compiler

A deterministic directive engine that converts explicit user instructions
into structured conversational state for LLM applications.

Modern language models reason well but are unreliable at maintaining
consistent state across interactions.

Corrections compete with earlier statements, constraints disappear,
and long conversations accumulate contradictions.

The **Context Compiler** introduces a deterministic state layer that governs authoritative conversational state independently of the model.

The model performs reasoning and generation while the compiler manages facts and constraints. Once accepted, directives remain authoritative until explicitly corrected or reset.

## Installation

- Python 3.11+
- `pip install context-compiler`
- Dev/test: `uv sync --group dev` and `uv run pytest`
- Examples: see [examples/README.md](examples/README.md)
- Demonstrations: see [demos/README.md](demos/README.md)

---

## 10-Second Example

User sets a constraint once:

```text
User: don't use peanuts
```

State becomes:

```json
{
  "facts": {
    "focus.primary": null
  },
  "policies": {
    "prohibit": ["peanuts"]
  },
  "version": 1
}
```

Later in the conversation:

```text
User: how should I make this curry?
```

The host supplies the authoritative state to the model so the constraint persists across turns.

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

The compiler governs authoritative conversational state and never calls the LLM.
The host decides whether to call the model based on the returned `Decision`.

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

### Host Integration Example

```python
engine = create_engine()
decision = engine.step(user_input)

if decision["kind"] == "clarify":
    show_to_user(decision["prompt_to_user"])
else:
    state = decision["state"] or engine.state
    messages = build_messages(state, user_input)
    render(call_llm(messages))
```

### API Reference

| API | Description |
|---|---|
| `create_engine(...)` | Create a new compiler engine, optionally with replacement initial state. |
| `step(user_input)` | Parse one user turn and return a deterministic `Decision`. |
| `engine.state` | Read or replace full in-memory authoritative state. |
| `export_json()` | Export current state as JSON for persistence/transport. |
| `import_json(payload)` | Load state from exported JSON payload. |

---

## State Model

The compiler maintains an authoritative state:

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

## State Access and Persistence

Hosts may inspect or replace in-memory state (`engine.state`) or persist it using `export_json()` and `import_json()`. State changes occur only through directives processed by `step()`. Storage is managed by the host application.

### Fact Schema

The current schema contains a single exclusive slot: `facts["focus.primary"]`.
This demonstrates deterministic fact replacement and correction behavior.
Richer schemas may be introduced in future releases.

### State Properties

- Facts are exclusive (last write wins)
- Policies are additive
- No inference or semantic reasoning

Identical input sequences always produce identical compiler state.
LLM responses may still vary unless deterministic decoding is used by the host.

---

## Directive Examples

Hard negative directive:

```text
User: don't use peanuts
```

Result:

```json
{
  "policies": {
    "prohibit": ["peanuts"]
  }
}
```

Fact configuration:

```text
User: use vegetarian curry
```

State update:

```text
facts.focus.primary = "vegetarian curry"
```

Correction:

```text
User: actually vegan curry
```

Result:

```text
facts.focus.primary = "vegan curry"
```

Ambiguous mutation:

```text
User: no use peanuts
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
  "facts": {"focus.primary": "vegetarian curry"},
  "policies": {"prohibit": ["peanuts"]},
  "version": 1
}
```

After `reset policies`:

```json
{
  "facts": {"focus.primary": "vegetarian curry"},
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

Integration examples are available in the [examples/](examples/) directory.

See [examples/README.md](examples/README.md) for walkthroughs.

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
uv run pytest
```

---

## Guarantees

- State changes only through explicit user directives or confirmation.
- Identical input sequences produce identical compiler state.
- Model responses never modify compiler state.
- Ambiguous directives trigger clarification instead of changing state.

These invariants are verified through behavioral tests and Hypothesis-based property tests.

---

## Design Notes

More detailed design and milestone documents are available in:

- [Project overview](docs/DescriptionAndMilestones.md)
- [M1 design document](docs/M1Design.md)

---

## License

Apache-2.0.
