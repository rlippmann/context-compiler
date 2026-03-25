
# Context Compiler

[![PyPI version](https://img.shields.io/pypi/v/context-compiler)](https://pypi.org/project/context-compiler/)
[![Python versions](https://img.shields.io/pypi/pyversions/context-compiler)](https://pypi.org/project/context-compiler/)
[![License](https://img.shields.io/pypi/l/context-compiler)](https://pypi.org/project/context-compiler/)

A deterministic directive engine that converts explicit user instructions
into structured conversational state for LLM applications.

Modern language models reason well but are unreliable at maintaining
consistent state across interactions.

Corrections compete with earlier statements, constraints disappear,
and long conversations accumulate contradictions.

The **Context Compiler** introduces a deterministic state layer that governs authoritative conversational state independently of the model.

The model performs reasoning and generation while the compiler manages facts and constraints. Once accepted, directives remain authoritative until explicitly corrected or reset.

## Why “Compiler”?

Context Compiler treats explicit user directives as inputs to a deterministic process.

Instead of relying on the LLM to remember constraints across a conversation, user instructions are compiled into structured state before the model runs.

The idea is similar to a traditional compiler: user directives are translated into a structured representation that the rest of the system can rely on.

## Installation

- Python 3.11+
- `pip install context-compiler`
- Dev/test: `uv sync --group dev` and `uv run pytest`

---

## 10-Second Example

User sets a constraint once:

```text
User: prohibit peanuts
```

Outcome: prohibited items now include `"peanuts"`.

Later in the conversation:

```text
User: how should I make this curry?
```

The host supplies the authoritative state to the model so the constraint persists across turns.

---

## Architecture

```text
User Input
     │
     ▼
Context Compiler
     │
     ▼
Decision
     │
     ▼
Host Application
 ├─ clarify → ask user
 ├─ passthrough → call LLM
 └─ update → call LLM with compiled state
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
|:-----------:|-----------------------------------------------|
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
| `create_engine(state=None)` | Create a new compiler engine; optional `state` provides initial authoritative state (validated/canonicalized). |
| `step(user_input)` | Parse one user turn and return a deterministic `Decision`. |
| `compile_transcript(messages)` | Replay a transcript from a fresh engine and return either final state or a confirmation prompt. |
| `engine.apply_transcript(messages)` | Replay a transcript onto the current engine state and return either final state or a confirmation prompt. |
| `engine.state` | Read current authoritative in-memory state snapshot. |
| `get_premise_value(state)` | Read the current premise value from a state snapshot. |
| `get_policy_items(state, value=None)` | Read policy items from a state snapshot (all, `use`, or `prohibit`). |
| `engine.export_json()` | Export current state as JSON for persistence/transport. |
| `engine.import_json(payload)` | Load/restore state from exported JSON payload. |

---

## State Model

The compiler maintains an authoritative state snapshot.
Hosts should treat this state as structured application data and avoid coupling
to internal field names or nested layout.

## State Access and Persistence

Hosts can provide initial state at engine creation (`create_engine(state=...)`),
read current in-memory state via `engine.state`, and persist/restore via
`export_json()` and `import_json()`. Semantic state mutations occur through
directives processed by `step()`. Storage is managed by the host application.

Use the returned state snapshot as structured host input for prompt
construction, policy enforcement, or replay/storage workflows.
For host code that needs typed reads without direct nested key lookups, use
`get_premise_value(state)` and `get_policy_items(state, value=...)`.

### Transcript Replay

Transcript replay compiles conversational history by reusing the same deterministic directive path:

- Only messages with `role == "user"` are processed.
- Assistant/system/non-user messages are ignored.
- Replay calls `step()` for each user message in order.
- Replay stops on the first clarification and returns a confirmation prompt.
- `compile_transcript(messages)` starts from a fresh engine.
- `engine.apply_transcript(messages)` applies replay onto the current engine state.

### State Properties

- Premise is a single slot (set once, then replaced via `change premise to ...`)
- Policies are per-item and exclusive by item (`use` or `prohibit`)
- No inference or semantic reasoning

Identical input sequences always produce identical compiler state.
LLM responses may still vary unless deterministic decoding is used by the host.

Premise replacement and policy mutation are always explicit via directives.
The engine does not infer intent from conversational wording outside the
documented grammar.

---

## Directive Examples

Set and change premise explicitly:

```text
User: set premise concise replies
User: change premise to concise bullet points
```

Result: premise is updated deterministically via explicit premise lifecycle commands.
Narrow near-miss premise `to` variants clarify (no mutation):
`set premise to <value>` and `change premise <value>`.

Per-item policy directives:

```text
User: use docker
User: prohibit peanuts
```

Result: policies store authoritative per-item states (`use` / `prohibit`).
Recognized empty payloads clarify without mutation:
`use`, `use   `, `prohibit`, and `prohibit   `.

Explicit replacement:

```text
User: use podman instead of docker
```

Result: remove `docker` use policy and set `podman` to `use` (or clarify if blocked).
Incomplete replacement payloads also clarify without mutation (for example:
`use x instead of`, `use  instead of y`, `use instead of y`).

Policy contradiction (clarify):

```text
User: use peanuts
User: prohibit peanuts
```

Result: compiler asks for clarification and leaves state unchanged.

## Policy Removal and Reset Commands

Policy cleanup commands are:

- `remove policy <item>` removes one policy item if present (idempotent update if absent)
- `reset policies` clears all policy items
- `clear state` resets premise and policies to initial values

Single-policy correction flow:

```text
User: prohibit peanuts
User: remove policy peanuts
User: use peanuts
```

Example:

- If policies include `{"docker": "use", "peanuts": "prohibit"}`:
- after `remove policy docker`, policies become `{"peanuts": "prohibit"}`.
- after `reset policies`, policies become `{}`.

---

## Examples

- [examples](examples/)
- [demos](demos/)
- [integrations](examples/integrations/)

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
- [Directive grammar specification](docs/DirectiveGrammarSpec.md)

---

## License

Apache-2.0.
