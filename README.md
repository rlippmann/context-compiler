# Context Compiler

[![PyPI version](https://img.shields.io/pypi/v/context-compiler)](https://pypi.org/project/context-compiler/)
[![Python versions](https://img.shields.io/pypi/pyversions/context-compiler)](https://pypi.org/project/context-compiler/)
[![License](https://img.shields.io/pypi/l/context-compiler)](https://pypi.org/project/context-compiler/)

Some behaviors require explicit host-side state handling.

Context Compiler is a deterministic conversational state authority for LLM applications.
It applies explicit premise and policy updates so state changes stay fixed and
repeatable.

## What prompting and reinjection can do

Prompting and reinjection are useful. In many real systems, reinjecting saved
state text is enough to keep instructions and policies persistent across turns.

Context Compiler adds host-owned transition rules for behaviors that plain text
reinjection does not implement by itself: replace `X` only if `X` exists, block
conflicting changes and ask for confirmation, and restore saved state plus
pending confirmations from checkpoints.

## What prompting cannot do by itself

Prompt text (including reinjected state text) helps, but it does not give your
app clear rules for when state can change. By itself, it does not provide:

- rules your app controls for state changes
- replacement precondition checks (`use X instead of Y` when `Y` may be absent)
- confirmation flows that must complete before anything else changes
- clear rules for when to block a change
- reliable checkpoint restore for both saved state and pending confirmation flow

## What Context Compiler provides

Context Compiler provides fixed host-side state handling:

- deterministic directive handling for explicit user state changes
- clarification instead of silent overwrite for blocked/ambiguous changes
- pending confirmation flows that must resolve before anything else changes
- checkpoint export/import for restoring saved state and pending confirmation flow
- structured saved state that the host can pass to the model

The model generates responses. The compiler owns state transitions.

## How the compiler metaphor works

Context Compiler treats important instructions as structured state instead of
temporary prompt text.

Like a compiler, it parses input, validates it, applies fixed rules, and
produces a stable representation the host can use. It is not source-code
compilation and not a reasoning model.

## Does it work?

Yes, on the current scored demo set.

- Scope: evaluated across **7 models** and **3 provider paths** (`ollama`, `openai`, `openai_compatible`).
- Scored checks (**6 demos per model**; Demo 6 excluded): baseline **26 / 42**, compiler **42 / 42**, compiler+compact **42 / 42**.
- Across tested models, compiler-mediated paths pass all scored scenarios; baseline behavior is model-dependent.

Interpretation guide:
- Demos `01`-`05` and `07` focus on persistence and policy-following behavior.
- Demos `08`/`09` focus on rules for when state is allowed to change.
- Demos `08`/`09` show what prompt text does not implement by itself.
- Plain reinjection can produce plausible responses, but it does not check whether replacement is allowed or wait for confirmation before saving changes.

→ [Full results and demo output](demos/README.md)
Canonical matrix: [docs/demos-results.md](docs/demos-results.md)

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

Context Compiler makes mutation rules explicit so behavior stays repeatable.

**Explicit directive**
```text
set premise concise replies
```
- Base model: silently accepts / rewrites
- Context Compiler: applies a repeatable state update

**State-dependent operation**
```text
clear state
use podman instead of docker
```
- Without explicit state transition rules: behavior depends on host/model handling
- Context Compiler: returns `clarify` before changing state

**Lifecycle enforcement**
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

The compiler owns state updates and never calls the LLM.
Your app decides whether to call the model based on the returned `Decision`.

---

## Quickstart

```bash
pip install context-compiler
context-compiler
context-compiler --with-preprocessor
context-compiler --json < input.txt
```

`context-compiler` launches the interactive REPL.

`--with-preprocessor` enables the experimental preprocessor before each REPL turn
(simple rule-based checks plus conservative validation). For near-miss inputs,
the preprocessor does not rewrite the text. It passes the input to the engine,
and the engine can return `clarify`.

`--json` enables machine-readable NDJSON output for non-interactive usage
(one complete JSON object per processed input line).

Preload options keep saved rules separate from in-progress confirmation state:
- `--initial-state-json` / `--initial-state-file` load saved state
  (via exported state JSON).
- `--initial-checkpoint-json` / `--initial-checkpoint-file` restore full
  continuation checkpoint (saved state + pending confirmation state).

REPL commands (controller layer, not engine directives):
- `state` shows current saved state.
- `preview <input>` runs deterministic dry-run without mutating live state.
- `step <input>` is an explicit alias of normal bare-input step behavior.

Bare REPL input behavior remains unchanged.

Or in code:
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

## FAQ

**Isn’t this just prompt engineering?**
It complements prompt engineering, but solves a different problem. Prompting
shapes model behavior. Context Compiler enforces state rules and updates state
only through explicit directives.

**Why not just use a plain dict?**
A plain dict is enough to drive prompt construction, schema selection, and
other host behavior.

Context Compiler solves a different problem: who updates that state, under what
rules, and what happens when instructions conflict.

```text
User: use python_script
User: prohibit python_script
```

With a plain dict, the application must invent conflict-resolution rules.
Context Compiler applies deterministic state-transition rules and can return
clarification instead of silently overwriting state.

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
| update      | authoritative state mutated; host may call LLM with updated state |
| clarify     | show `prompt_to_user` and do not call the LLM |

For normal app code, prefer exported decision helpers (`is_clarify`,
`is_update`, `is_passthrough`, `get_clarify_prompt`, `get_decision_state`)
instead of direct key traversal.

---

### API Reference

| API | Description |
|---|---|
| `create_engine(state=None)` | Create a new compiler engine; optional `state` provides initial authoritative state (validated/canonicalized). |
| `step(user_input)` | Parse one user turn and return a deterministic `Decision`. |
| `compile_transcript(messages: Transcript)` | Replay a transcript from a fresh engine and return either final state or a confirmation prompt. |
| `engine.apply_transcript(messages: Transcript)` | Replay a transcript onto the current engine state and return either final state or a confirmation prompt. |
| `engine.state` | Read the current opaque authoritative in-memory state snapshot; for normal host reads, prefer `get_premise_value(state)` and `get_policy_items(state, ...)`. |
| `engine.has_pending_clarification()` | Return whether a confirmation-required clarification is currently pending. |
| `get_premise_value(state)` | Read the current premise value from a state snapshot. |
| `get_policy_items(state, value=None)` | Read policy items from a state snapshot (all, `use`, or `prohibit`). |
| `engine.export_json()` | Export authoritative state as JSON (`str`) for state transport/persistence. |
| `engine.import_json(payload)` | Load/restore authoritative state from exported JSON (`str`). |
| `engine.export_checkpoint()` | Export resumable checkpoint object (`Checkpoint`). |
| `engine.import_checkpoint(payload)` | Restore full checkpoint (`Checkpoint`) and return `None`. |
| `engine.export_checkpoint_json()` | Export checkpoint as canonical JSON (`str`). |
| `engine.import_checkpoint_json(payload)` | Restore checkpoint from JSON (`str`) and return `None`. |

### Controller API (Reusable Outside REPL)

These controller APIs are public package exports and can be used directly
in app code (not just inside the REPL).

Controller quick example:

```python
from context_compiler import (
    diff_has_changes,
    get_step_decision,
    get_step_state,
    is_update,
    get_preview_state_after,
    create_engine,
    preview,
    preview_would_mutate,
    state_diff,
    step,
)

engine = create_engine()

before = engine.state
dry_run = preview(engine, "prohibit peanuts")
print(preview_would_mutate(dry_run))  # True
planned_change = state_diff(before, get_preview_state_after(dry_run))
print(diff_has_changes(planned_change))  # True

after_preview = engine.state
print(diff_has_changes(state_diff(before, after_preview)))  # False (preview does not mutate state)

applied = step(engine, "prohibit peanuts")
print(is_update(get_step_decision(applied)))  # True
print(get_step_state(applied) is not None)  # True
```

| API | Description |
|---|---|
| `step(engine, user_input)` | Run one turn through the engine and return `StepResult` (`output_version`, `mode`, `decision`, `state`). |
| `preview(engine, user_input)` | Run deterministic dry-run preview and return `PreviewResult` (`output_version`, `mode`, `decision`, `state_before`, `state_after`, `diff`, `would_mutate`). Live engine state is restored after preview. |
| `state_diff(state_before, state_after)` | Return a structural `StructuralDiff` (`changed`, premise before/after, policies added/removed/changed). |

Decision-kind constants are also exported for host branching readability:
- `DECISION_PASSTHROUGH`
- `DECISION_UPDATE`
- `DECISION_CLARIFY`

Decision helpers are also exported for common host-side checks:
- `is_update(decision)`
- `is_clarify(decision)`
- `is_passthrough(decision)`
- `get_clarify_prompt(decision)`
- `get_decision_state(decision)`

Policy value constants are exported for explicit policy comparisons:
- `POLICY_USE`
- `POLICY_PROHIBIT`

---

## State Model

The state model represents explicit user commitments that the host can treat as
authoritative for future turns.

- `premise` = authoritative context that changes how future answers should be interpreted
- `use` = affirmative selection or preference
- `prohibit` = explicit exclusion

The compiler keeps this state snapshot in a form that your app can trust.

- Premise is a single value that can be set or replaced
- Policies are per-item (`use` or `prohibit`)
- State changes only through explicit directives
- No inference or semantic reasoning

Identical input sequences always produce identical state.

The internal structure of the state is intentionally opaque to host applications.
For normal reads, prefer `get_premise_value(state)` and
`get_policy_items(state, ...)` over direct key traversal.

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

### Example domains

Hosts define what policy items and premise mean in context. Common patterns:

- safety-oriented constraints (for example, prohibited materials or tools)
- authority/evidence constraints (for example, cite only approved sources)
- software workflow constraints (for example, require `uv`, prohibit `npm`)
- accessibility/environment constraints (for example, no audio-only outputs)

Context Compiler enforces explicit directive/state mechanics. Domain reasoning
still belongs to the host and model workflow.

---

## Checkpoint Contract

`export_json()` / `import_json()` and checkpoint APIs serve different boundaries:

- `export_json()` / `import_json()` transport **authoritative state only**
- checkpoint APIs transport **serialized continuation**:
  - authoritative state
  - pending confirmation flow state

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

The checkpoint shape above is an explicit serialization contract. At this
boundary, direct key access is expected.

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
- preserve pending confirmation flow state (`pending`) across process/request boundaries.

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

Integration note: current OpenWebUI example pipes return deterministic local
acknowledgements for directive-only `update` decisions instead of forwarding
those turns to the downstream LLM.

---

## Advanced topics

### Guarantees

- State changes only through explicit user directives or confirmation.
- Identical input sequences produce identical compiler state.
- Model responses never modify compiler state.
- Ambiguous directives trigger clarification instead of changing state.

These invariants are verified through behavioral tests and Hypothesis-based property tests.

### Optional: LLM Preprocessor (Experimental)

An optional host-side preprocessor can conservatively convert some natural-language instructions
into canonical directives before compilation.

It is designed to be conservative and must be used with validation:

- reject-first; directive-adjacent unsafe forms abstain instead of rewriting
- all outputs must be validated with `parse_preprocessor_output(...)`
- no directive grammar expansion
- raw outputs must not be passed directly to the compiler

If `engine.has_pending_clarification()` is true, bypass preprocessing and pass raw input directly to `engine.step(...)`.
Boundary policy is false-negative-preferred: abstain rather than risk unsafe state mutation.

See [LLM preprocessor](docs/llm-preprocessor.md) and
[`experimental/preprocessor/`](experimental/preprocessor/) for details.

### Multiple engines

- [Multiple engines](docs/multi-engine.md)

For a full documentation map, see [docs/README.md](docs/README.md).

---

## Design Notes

More detailed design and milestone documents are available in:

- [Design philosophy](docs/DesignPhilosophy.md)
- [Architecture boundaries](docs/architecture.md)
- [Project overview](docs/DescriptionAndMilestones.md)
- [Directive grammar specification](docs/DirectiveGrammarSpec.md)

---

### Conformance Fixtures

Cross-language conformance tests are defined in [`tests/fixtures/`](tests/fixtures/).
These fixtures serve as the behavioral contract for compiler semantics across implementations.

---

## License

Apache-2.0.
