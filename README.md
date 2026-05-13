
# Context Compiler

[![PyPI version](https://img.shields.io/pypi/v/context-compiler)](https://pypi.org/project/context-compiler/)
[![Python versions](https://img.shields.io/pypi/pyversions/context-compiler)](https://pypi.org/project/context-compiler/)
[![License](https://img.shields.io/pypi/l/context-compiler)](https://pypi.org/project/context-compiler/)

A deterministic directive engine that converts explicit user instructions
into structured conversational state for LLM applications.

LLMs are good at reasoning but unreliable at maintaining consistent state. Constraints drift, corrections compete, and long conversations accumulate contradictions.

The **Context Compiler** introduces a deterministic state layer that governs authoritative conversational state independently of the model.

The model performs reasoning and generation while the compiler manages premise and policies. Once accepted, directives remain authoritative until explicitly corrected or reset.

## Does it work?

Yes, on the current scored demo set.

- Scope: evaluated across **7 models** and **3 provider paths** (`ollama`, `openai`, `openai_compatible`).
- Scored checks (**6 demos per model**; Demo 6 excluded): baseline **26 / 42**, compiler **42 / 42**, compiler+compact **42 / 42**.
- Across tested models, compiler-mediated paths pass all scored scenarios; baseline behavior is model-dependent.

→ [Full results and demo output](demos/README.md)  
Canonical matrix: [docs/demos-results.md](docs/demos-results.md)

## Quickstart

```bash
pip install context-compiler
context-compiler
context-compiler --with-preprocessor
```

`context-compiler` launches the interactive REPL.

`--with-preprocessor` enables the experimental preprocessor before each REPL turn
(heuristic + validation only). Near-miss inputs are not rewritten and are
passed through to the engine, which continues to return clarify behavior for
those forms.

Or in code:
```python
from context_compiler import create_engine

engine = create_engine()

user_input = "prohibit peanuts"
decision = engine.step(user_input)

if decision["kind"] == "clarify":
    show_to_user(decision["prompt_to_user"])
elif decision["kind"] == "update":
    messages = build_messages(engine.state, user_input)
    render(call_llm(messages))
else:
    render(call_llm(user_input))
```

## Installation

Requirements:
- Python 3.11+

Install:
```bash
pip install context-compiler
```

Packaging notes:
- Base install includes core engine modules and `examples/` artifacts.
- LLM demos require: `pip install "context-compiler[demos]"`.
- Optional preprocessor support: `pip install "context-compiler[experimental]"`.
- Integration-oriented dependency support: `pip install "context-compiler[integrations]"`.
- LiteLLM Proxy example dependency bundle: `pip install "context-compiler[litellm_proxy]"`.
- Host runtimes (for example, Open WebUI) are not installed by `integrations`.

### Development

```bash
uv sync --group dev
uv run pytest
```

---

## Why “Compiler”?

Context Compiler treats explicit user directives as inputs to a deterministic process.

Instead of relying on the LLM to remember constraints across a conversation, user instructions are compiled into structured state before the model runs.

The idea is similar to a traditional compiler: user directives are translated into a structured representation that the rest of the system can rely on.

---

## 10-Second Example

User sets a constraint once:

```text
User: prohibit peanuts
```

Outcome: policy state includes `"peanuts": "prohibit"`.

Later in the conversation:

```text
User: how should I make this curry?
```

The host supplies the authoritative state to the model so the constraint persists across turns.

---

## Deterministic behavior (examples)

LLMs interpret intent. Context Compiler enforces it.

**Explicit directive**
```text
set premise concise replies
```
- Base model: silently accepts / rewrites
- Context Compiler: applies a deterministic state update

**State-dependent operation**
```text
clear state
use podman instead of docker
```
- Base model: generic explanation
- Context Compiler: rejects (“No exact policy found for 'docker'…”)

**Lifecycle enforcement**
```text
clear state
change premise to formal tone
```
- Base model: conversational rewrite guidance
- Context Compiler: clarifies (“No premise exists yet…”)

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

The compiler governs authoritative state and never calls the LLM.
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

---

### API Reference

| API | Description |
|---|---|
| `create_engine(state=None)` | Create a new compiler engine; optional `state` provides initial authoritative state (validated/canonicalized). |
| `step(user_input)` | Parse one user turn and return a deterministic `Decision`. |
| `compile_transcript(messages: Transcript)` | Replay a transcript from a fresh engine and return either final state or a confirmation prompt. |
| `engine.apply_transcript(messages: Transcript)` | Replay a transcript onto the current engine state and return either final state or a confirmation prompt. |
| `engine.state` | Read current authoritative in-memory state snapshot. |
| `get_premise_value(state)` | Read the current premise value from a state snapshot. |
| `get_policy_items(state, value=None)` | Read policy items from a state snapshot (all, `use`, or `prohibit`). |
| `engine.export_json()` | Export authoritative state as JSON (`str`) for state transport/persistence. |
| `engine.import_json(payload)` | Load/restore authoritative state from exported JSON (`str`). |
| `engine.export_checkpoint()` | Export resumable checkpoint object (`Checkpoint`). |
| `engine.import_checkpoint(payload)` | Restore full checkpoint (`Checkpoint`) and return `None`. |
| `engine.export_checkpoint_json()` | Export checkpoint as canonical JSON (`str`). |
| `engine.import_checkpoint_json(payload)` | Restore checkpoint from JSON (`str`) and return `None`. |

---

## State Model

The compiler maintains an authoritative state snapshot.

- Premise is a single value that can be set or replaced
- Policies are per-item (`use` or `prohibit`)
- State changes only through explicit directives
- No inference or semantic reasoning

Identical input sequences always produce identical state.

The internal structure of the state is intentionally opaque to host applications.

---

## Checkpoint Contract

`export_json()` / `import_json()` and checkpoint APIs serve different boundaries:

- `export_json()` / `import_json()` transport **authoritative state only**
- checkpoint APIs transport **serialized continuation**:
  - authoritative state
  - pending confirmation-required continuation state

Checkpoint object shape:

```json
{
  "checkpoint_version": 1,
  "authoritative_state": {
    "premise": "concise replies",
    "policies": {
      "docker": "use"
    },
    "version": 2
  },
  "pending": {
    "kind": "replacement",
    "replacement": {
      "kind": "use_only",
      "new_item": "kubectl",
      "old_item": null
    },
    "prompt_to_user": "..."
  }
}
```

Notes:

- `pending` is `null` when no continuation is waiting for confirmation.
- `pending` captures confirmation-required operations (for example replacement flows).
- `old_item` may be `null` for `"use_only"` when confirming “use X instead?” without an existing exact policy to replace.
- imported policy keys are normalized during `import_json` / checkpoint authoritative-state restore.
- if a policy key normalizes to `""`, the payload is invalid and is rejected.
- this keeps import-time state integrity aligned with directive-time behavior where empty policy items are not allowed.
- checkpoint restore is full and deterministic: authoritative state and pending continuation are restored together.
- checkpoint validation is all-or-nothing; invalid payloads raise and no partial restore occurs.
- `checkpoint_version` is independent of authoritative state `version` and must be bumped when checkpoint contract shape changes (especially `pending`).

When to use checkpoint APIs:

- stateless host/integration boundaries where engine instances are short-lived.
- resume after interruption without losing pending clarification flow.
- preserve confirmation-required continuation state (`pending`) across process/request boundaries.

---

### When to use `premise`

The `premise` is intended for **persistent context that changes how all answers should be interpreted**, especially when it:

- applies across many turns
- significantly changes what solutions are valid
- cannot be fully captured as simple `use` / `prohibit` policies

Examples:

- “Current medications: …”
- “Outdoor event; no seating available”
- “GDPR data handling requirements apply”
- “System is deployed across multiple regions”
- “Limited time available”

In these cases, the premise acts as an **authoritative context anchor** that the host supplies to the model on every turn.

Use policies instead when the constraint is explicit and enforceable:

- “prohibit foods that may cause GI upset”
- “use handheld foods”
- “prohibit storing personal data beyond immediate use”
- “prohibit introducing new external dependencies”
- “use single-step preparation methods”

---

## Directive Examples

Set and change premise:

```text
User: set premise concise replies
User: change premise to concise bullet points
```

Per-item policies:

```text
User: use docker
User: prohibit peanuts
```

Replacement:

```text
User: use podman instead of docker
```

Removal and reset:

```text
User: remove policy peanuts
User: reset policies
User: clear state
```

Conflicting directives trigger clarification instead of changing state.

For full directive grammar and edge-case behavior, see [DirectiveGrammarSpec.md](docs/DirectiveGrammarSpec.md).

---

## Examples

- [examples](examples/) — minimal usage patterns and core integration primitives
- [demos](demos/) — concrete scenarios showing how behavior differs with and without the compiler
- [integrations](examples/integrations/) — production-style host integrations (OpenWebUI, LiteLLM, etc.)

---

## Guarantees

- State changes only through explicit user directives or confirmation.
- Identical input sequences produce identical compiler state.
- Model responses never modify compiler state.
- Ambiguous directives trigger clarification instead of changing state.

These invariants are verified through behavioral tests and Hypothesis-based property tests.

---

## Optional: LLM Preprocessor (Experimental)

An optional host-side preprocessor can conservatively convert some natural-language instructions
into canonical directives before compilation.

It is designed to be conservative and must be used with validation:

- reject-first; directive-adjacent unsafe forms abstain instead of rewriting
- all outputs must be validated with `parse_preprocessor_output(...)`
- no directive grammar expansion
- raw outputs must not be passed directly to the compiler

See [LLM preprocessor](docs/llm-preprocessor.md) and
[`experimental/preprocessor/`](experimental/preprocessor/) for details.


## Advanced topics

- [Multiple engines](docs/multi-engine.md)

For a full documentation map, see [docs/README.md](docs/README.md).

---

## Design Notes

More detailed design and milestone documents are available in:

- [Project overview](docs/DescriptionAndMilestones.md)
- [Directive grammar specification](docs/DirectiveGrammarSpec.md)

---

## Conformance Fixtures

Cross-language conformance tests are defined in [`tests/fixtures/`](tests/fixtures/).
These fixtures serve as the behavioral contract for compiler semantics across implementations.

---

## License

Apache-2.0.
