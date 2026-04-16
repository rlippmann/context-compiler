
# Context Compiler

[![PyPI version](https://img.shields.io/pypi/v/context-compiler)](https://pypi.org/project/context-compiler/)
[![Python versions](https://img.shields.io/pypi/pyversions/context-compiler)](https://pypi.org/project/context-compiler/)
[![License](https://img.shields.io/pypi/l/context-compiler)](https://pypi.org/project/context-compiler/)

A deterministic directive engine that converts explicit user instructions
into structured conversational state for LLM applications.

LLMs are good at reasoning but unreliable at maintaining consistent state. Constraints drift, corrections compete, and long conversations accumulate contradictions.

The **Context Compiler** introduces a deterministic state layer that governs authoritative conversational state independently of the model.

The model performs reasoning and generation while the compiler manages premise and policies. Once accepted, directives remain authoritative until explicitly corrected or reset.

## Quickstart

```bash
pip install context-compiler
context-compiler
```

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
| `engine.export_json()` | Export current state as JSON for persistence/transport. |
| `engine.import_json(payload)` | Load/restore state from exported JSON payload. |

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

- [examples](examples/)
- [demos](demos/)
- [integrations](examples/integrations/)

---

## Guarantees

- State changes only through explicit user directives or confirmation.
- Identical input sequences produce identical compiler state.
- Model responses never modify compiler state.
- Ambiguous directives trigger clarification instead of changing state.

These invariants are verified through behavioral tests and Hypothesis-based property tests.

---

## Evidence

### Behavioral correctness (key examples)

Concrete behavioral comparisons (base model vs compiler) are available here:

- [Open WebUI integration README](examples/integrations/openwebui/README.md)

These demonstrate deterministic clarification, state enforcement, and conflict handling.

### Cross-model evaluation

- Models tested: `llama3.1:8b`, `gpt-4o-mini`, `gpt-4.1`, `gpt-5`, `claude-sonnet-4`, `claude-opus-4`
- Pass-rate summary: baseline (LLM only) `2–4 / 6`; with compiler `6 / 6`; with compiler + compaction `6 / 6`.

### Efficiency

- Context reduction in long conversations: up to `99%`
- Prompt size reduction: about `50%`

### Additional results

- [SWE curated results (compiler vs baseline)](evals/swe-bench/README.md) — cross-model evaluation on 6 tasks showing mostly positive deltas


---


## Optional: LLM Preprocessor (Experimental)

An optional host-side preprocessor can convert natural-language instructions
into canonical directives before compilation.

It is designed to be conservative and must be used with validation:

- heuristic-first, with LLM fallback when needed
- all outputs must be validated with `parse_precompiler_output(...)`
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

---

## License

Apache-2.0.
