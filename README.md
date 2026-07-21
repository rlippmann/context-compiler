# Context Compiler

[![PyPI version](https://img.shields.io/pypi/v/context-compiler)](https://pypi.org/project/context-compiler/)
[![Python versions](https://img.shields.io/pypi/pyversions/context-compiler)](https://pypi.org/project/context-compiler/)
[![License](https://img.shields.io/pypi/l/context-compiler)](https://pypi.org/project/context-compiler/)

Context Compiler is a deterministic conversational state authority for LLM applications.
It handles canonical directive execution, semantic validation, deterministic
clarify decisions, checkpoint restore, and structured authoritative state for
the host.

## What Context Compiler provides

Context Compiler gives hosts fixed state rules:

- handle canonical explicit state changes with deterministic rules
- clarification instead of silent overwrite for blocked/ambiguous changes
- export and import checkpoints to restore saved state in a versioned engine snapshot
- produce structured authoritative state for downstream host decisions

The model generates responses. The compiler owns state.
Human-facing normalization, malformed-input recovery, and intent drafting belong
outside core.

## How the compiler metaphor works

Like a compiler, it parses canonical directives, validates them, applies fixed rules, and
produces a stable result the host can use. It treats important instructions as
structured state instead of temporary prompt text. It is not source-code
compilation, not a reasoning model, and not a natural-language repair layer.

## 10-Second Example

User sets a premise once:

```text
User: set premise current project uses uv
```

Outcome: premise state includes `"current project uses uv"`.

Later in the conversation:

```text
User: how should I run the tests?
```

Your host sends the saved authoritative state with this later request, so the
model answers in the context of the saved premise (`current project uses uv`)
instead of relying on memory of earlier conversation text.

---

## Deterministic behavior (examples)

Context Compiler makes state-change rules explicit so behavior stays repeatable.

### Explicit directive

```text
set premise concise replies
```

- Base model: silently accepts / rewrites
- Context Compiler: applies a repeatable state update

### Single-directive grammar

```text
use docker and prohibit peanuts
```

- Without an authority layer: host/model behavior varies
- Context Compiler: returns `clarify`, keeps authoritative state unchanged, and asks for separate directives

### State-dependent operation

```text
clear state
use podman instead of docker
```

- Without explicit state transition rules: behavior depends on host/model handling
- Context Compiler: returns `clarify` before changing state

### Lifecycle enforcement

```text
clear state
change premise to formal tone
```

- Without explicit transition checks: behavior depends on host/model handling
- Context Compiler: asks for clarification and keeps saved state unchanged

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
 └─ update → authoritative state mutated; host may call LLM with compiled state
```

The compiler never calls the LLM. Your app decides what to do with the returned
`Decision`.

---

## Quickstart

Use Context Compiler in your host application first:

```python
from context_compiler import (
    create_engine,
    get_clarify_prompt,
    is_clarify,
    is_update,
)

engine = create_engine()

user_input = "set premise current project uses uv"
decision = engine.step(user_input)

if is_clarify(decision):
    show_to_user(get_clarify_prompt(decision))
elif is_update(decision):
    messages = build_messages(engine.state, user_input)
    render(call_llm(messages))
else:
    render(call_llm(user_input))
```

This is the main integration path: your app owns the model call and uses the
compiler as the authority layer for state transitions.

For runnable application-layer examples, see
[`context-compiler-example-integrations`](https://github.com/rlippmann/context-compiler-example-integrations).
That companion repository shows enforcement points built on compiler state,
including retrieval filtering, schema selection, tool gating, execution
authorization, gateway middleware, checkpoint continuation, and prompt
construction.

## Does it Work?

Yes. The current demo suite in this repository contains 8 scored demos
(`01`-`05`, `07`, `08`, `09`) plus 1 informational demo (`06`).

The current published verification matrix combines 7 current model runs across
hosted/frontier providers and local Ollama models. In those current runs,
baseline passed **24 / 56**, reinjected-state passed **40 / 56**, and both
compiler paths passed **56 / 56**.

→ [Current demo set and output modes](demos/README.md)
Current and historical published results: [docs/demos-results.md](docs/demos-results.md)

## Interactive Playground

Use the REPL to explore behavior, learn the directive grammar, and debug or
test host-side state rules.

```bash
pip install context-compiler
context-compiler
```

Preload options keep authoritative state transport separate from checkpoint session snapshots:

- `--initial-state-json` / `--initial-state-file` load saved state
  (via exported state JSON).
- `--initial-checkpoint-json` / `--initial-checkpoint-file` restore the full
  checkpoint envelope (saved state plus reserved continuation field).

REPL commands (controller layer, not engine directives):

- `state` shows current saved state.
- `preview <input>` runs deterministic dry-run without mutating live state.
- `step <input>` is an explicit alias of normal bare-input step behavior.

Bare REPL input behavior remains unchanged.

## Machine-Readable CLI Usage

Use `--json` when you want one complete JSON object per processed input line
for non-interactive usage.

```bash
context-compiler --json < input.txt
```

Preload options keep authoritative state transport separate from checkpoint session snapshots:

- `--initial-state-json` / `--initial-state-file` load saved state
  (via exported state JSON).
- `--initial-checkpoint-json` / `--initial-checkpoint-file` restore the full
  checkpoint envelope (saved state plus reserved continuation field).

## Installation

Requirements:

- Python 3.11+

Install:

```bash
pip install context-compiler
```

Packaging notes:

- Base install includes the core authority-layer engine and CLI.
- Example and demo source files are available in the repository and source distribution.
- To run the demos from this repository, clone the repo and install `context-compiler[demos]`.
- The `[demos]` extra installs optional dependencies such as LiteLLM. It does not install demo source files into site-packages.

### Development

```bash
uv sync --group dev
uv run pytest
```

## Decision API

Each user message produces a `Decision`.

```python
class Decision(TypedDict):
    kind: Literal["passthrough", "update", "clarify"]
    state: dict | None
    prompt_to_user: str | None
```

Meaning:

| kind | host behavior |
| --- | --- |
| passthrough | forward user input to LLM |
| update | authoritative state mutated; host may call LLM with updated state |
| clarify | show `prompt_to_user` and do not call the LLM |

For normal app code, prefer the exported decision helpers (`is_clarify`,
`is_update`, `is_passthrough`, `get_clarify_prompt`, `get_decision_state`)
instead of direct key traversal.

See [docs/api-reference.md](docs/api-reference.md) for the full public API
reference.

Common API entry points:

- engine lifecycle: `create_engine(...)`, `engine.step(...)`, `engine.state`,
  `engine.has_pending_clarification()`
- decision helpers: `is_clarify(...)`, `is_update(...)`, `is_passthrough(...)`,
  `get_clarify_prompt(...)`, `get_decision_state(...)`
- state helpers: `get_premise_value(...)`, `get_policy_items(...)`
- state and checkpoint transport: `export_json(...)`, `import_json(...)`,
  `export_checkpoint(...)`, `import_checkpoint(...)`
- controller APIs: `preview(...)`, `step(...)`, `state_diff(...)`

### Controller API (Reusable Outside REPL)

- `preview(engine, user_input)` performs a deterministic dry run and restores
  live engine state afterward
- `step(engine, user_input)` returns a reusable result envelope around one
  engine turn
- `state_diff(state_before, state_after)` summarizes structural state changes

For examples and helper accessors such as `get_step_decision(...)`,
`get_preview_state_after(...)`, `preview_would_mutate(...)`, and
`diff_has_changes(...)`, see [docs/api-reference.md](docs/api-reference.md).

---

## State Model

The state model holds explicit user commitments that the host can treat as
authoritative in future turns.

- `premise` = authoritative context that changes how future answers should be interpreted
- `use` = affirmative selection or preference
- `prohibit` = explicit exclusion

- Premise is a single value that can be set or replaced
- Policies are per-item (`use` or `prohibit`)
- State changes only through explicit directives
- No inference or semantic reasoning
- Non-canonical input normalization is outside the core state contract

Identical input sequences always produce identical state.

The internal structure of the state is intentionally opaque to host applications.
For normal reads, prefer `get_premise_value(state)` and
`get_policy_items(state, ...)` over direct key traversal.

---

### When to use `premise`

Use `premise` for **persistent context that changes how all answers should be interpreted**, especially when it:

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

### Example domains

Hosts define what policy items and premise mean in context. Common patterns include:

- safety-oriented constraints (for example, prohibited materials or tools)
- authority/evidence constraints (for example, cite only approved sources)
- software workflow constraints (for example, require `uv`, prohibit `npm`)
- accessibility/environment constraints (for example, no audio-only outputs)

Context Compiler enforces explicit directive and state rules. Domain reasoning
still belongs to the host and model workflow.

If a user says something non-canonical such as a near miss, alternate phrasing,
or a failed replacement request that would need reinterpretation, that
normalization is outside core and must happen before canonical directives reach
the compiler.

---

## Checkpoint Contract

`export_json()` / `import_json()` and the checkpoint APIs serve different boundaries:

- `export_json()` / `import_json()` transport **authoritative state only**
- checkpoint APIs transport a **versioned engine snapshot**:
  - authoritative state
  - reserved `pending` field for canonical continuation compatibility

Use state JSON when you only need authoritative state. Use checkpoint APIs when
you want the stable checkpoint envelope across process or request boundaries.

For the checkpoint object shape, API-level usage notes, and serialization
details, see [docs/api-reference.md](docs/api-reference.md#checkpoint-apis).

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

Grammar invariant: one input may contain at most one canonical directive.
If another canonical directive start appears later in the same input, the
input is invalid and Context Compiler returns `clarify` without mutating
authoritative state or creating pending continuation state.

Examples:

```text
Valid:
use docker
use podman instead of docker
clear state

Invalid:
use docker and prohibit peanuts
set premise vegetarian and use docker
clear state then set premise new project
```

Quote behavior follows the current grammar literally:

```text
Passthrough:
"use docker and prohibit peanuts"

Invalid:
use "docker and prohibit peanuts"
set premise "use docker and prohibit peanuts"
```

Quotes do not create protected literal regions inside a recognized directive
payload.

Conflicting directives also trigger clarification instead of changing state.

For full directive grammar and edge-case behavior, see [DirectiveGrammarSpec.md](docs/DirectiveGrammarSpec.md).

---

## Examples

- [examples](examples/) — minimal usage patterns for the core authority layer
- [demos](demos/) — concrete scenarios showing how behavior differs with and without the compiler
- [`context-compiler-example-integrations`](https://github.com/rlippmann/context-compiler-example-integrations) — runnable application-layer enforcement examples built around compiler state

---

## FAQ

**Isn't this just prompt reinjection?**
No. Prompt construction is one downstream use of authoritative state.
Context Compiler is the authority layer that decides when state changes are
allowed, when clarification is required, and how continuation state is
restored. For runnable application-layer examples, see
[`context-compiler-example-integrations`](https://github.com/rlippmann/context-compiler-example-integrations).

Human-facing interpretation is a separate concern. If you want to recognize
non-canonical phrasing, recover from malformed input, narrow user intent, or
turn a failed replacement request into a different canonical directive, do that
before calling core.

**Why not just use a plain dict?**
A plain dict can hold state for prompt construction, schema selection, tool
gating, and other host behavior.

Context Compiler solves the authority problem: who updates that state, under
which rules, and what happens when instructions conflict.

```text
User: use python_script
User: prohibit python_script
```

Without an authority layer, the application must invent conflict-resolution and
continuation rules itself. Context Compiler applies deterministic
state-transition rules and can return clarification instead of silently
overwriting state.

---

## Advanced topics

### Guarantees

- State changes only through explicit user directives or confirmation.
- Identical input sequences produce identical compiler state.
- Model responses never modify compiler state.
- Ambiguous directives trigger clarification instead of changing state.

Behavioral tests and Hypothesis-based property tests verify these invariants.

### Multiple engines

- [Multiple engines](docs/multi-engine.md)

For a full documentation map, see [docs/README.md](docs/README.md).

---

## Design Notes

These docs cover the design and milestone details:

- [Design philosophy](docs/DesignPhilosophy.md)
- [Architecture boundaries](docs/architecture.md)
- [Project overview](docs/DescriptionAndMilestones.md)
- [Directive grammar specification](docs/DirectiveGrammarSpec.md)

---

### Conformance Fixtures

[`tests/fixtures/`](tests/fixtures/) defines the cross-language conformance tests.
These fixtures serve as the behavioral contract for compiler semantics across implementations.

## Development Process

Most of this project and related projects were implemented with Codex across many development sessions, including substantial implementation, refactoring, and cross-language porting work. ChatGPT was used separately for design discussion, review, and planning. Conformance harnesses and tests were used to verify behavioral consistency rather than treating model output as the correctness check.

---

## License

Apache-2.0.
