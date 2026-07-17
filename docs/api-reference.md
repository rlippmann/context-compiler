# API Reference

Public API reference for `context_compiler`.

This page documents the exported package surface and typical usage patterns. It
does not redefine behavioral semantics.

Authoritative behavior documents:

- [Directive Grammar Specification](DirectiveGrammarSpec.md)
- [Architecture boundaries](architecture.md)
- [Project README](../README.md)

For behavioral semantics, use the authoritative documents above. This page
documents the public checkpoint APIs and their contract surface without
redefining directive or continuation behavior.

## Engine Lifecycle

### `create_engine(state=None)`

Create a new engine instance.

- `state=None`: start from empty authoritative state
- `state=<State>`: initialize from a validated authoritative state snapshot

Typical use:

```python
from context_compiler import create_engine

engine = create_engine()
```

### `engine.step(user_input)`

Parse one user turn and return a deterministic `Decision`.

Typical use:

```python
decision = engine.step("set premise current project uses uv")
```

Behavior for directive handling, clarification, and confirmation flows is
defined by the [Directive Grammar Specification](DirectiveGrammarSpec.md).

Important grammar contract:

- one input may contain at most one canonical directive
- if a later canonical directive start appears in the same input, `engine.step(...)`
  returns the normal `clarify` decision contract
- compound directives do not mutate authoritative state and do not create
  pending clarification or replacement state
- quote characters do not create protected literal regions inside recognized
  directive payloads

### `context_compiler.grammar`

Canonical grammar helpers are available from the `context_compiler.grammar`
submodule.

Public grammar surface:

- `DirectiveKind`
- `ValidatedDirective`
- `validate_directive(text)`
- `is_canonical_directive(text)`
- `render_directive(kind, /, **operands)`

Use this surface for exact canonical validation or canonical directive string
construction only.

Boundary notes:

- no public parser is exposed
- validation returns `None` for any non-canonical input, including near misses,
  compounds, and ordinary prose
- rendering is syntax-only and performs no state interpretation
- `engine.step(...)` remains the authority for clarification, state
  transitions, pending confirmation, and mutation behavior

### `engine.state`

Read the current authoritative in-memory state snapshot.

The internal structure is intentionally opaque for normal host use. Prefer
`get_premise_value(state)` and `get_policy_items(state, ...)` over direct key
traversal unless you are working at an explicit serialization boundary.

### `engine.has_pending_clarification()`

Return whether a confirmation-required clarification is currently pending.

Typical use:

```python
if engine.has_pending_clarification():
    show_pending_ui()
```

## Decision API

Each user message produces a `Decision`.

```python
class Decision(TypedDict):
    kind: Literal["passthrough", "update", "clarify"]
    state: dict | None
    prompt_to_user: str | None
```

Decision kinds:

| kind | Intended host use |
| --- | --- |
| `passthrough` | forward the user input to the model/runtime |
| `update` | authoritative state changed; host may apply downstream behavior using updated state |
| `clarify` | show `prompt_to_user`; do not continue normal downstream processing yet |

Helper functions:

- `is_passthrough(decision)`
- `is_update(decision)`
- `is_clarify(decision)`
- `get_clarify_prompt(decision)`
- `get_decision_state(decision)`

Typical use:

```python
from context_compiler import get_clarify_prompt, is_clarify, is_update

decision = engine.step(user_input)

if is_clarify(decision):
    show_to_user(get_clarify_prompt(decision))
elif is_update(decision):
    apply_runtime_rules()
```

## State Access

Use the exported helpers for normal reads from a `State` snapshot.

### Premise helpers

- `get_premise_value(state)` returns the current premise value or `None`

### Policy helpers

- `get_policy_items(state)` returns all policy items
- `get_policy_items(state, "use")` returns `use` items
- `get_policy_items(state, "prohibit")` returns `prohibit` items

Typical use:

```python
from context_compiler import POLICY_PROHIBIT, get_policy_items

blocked_tools = get_policy_items(state, POLICY_PROHIBIT)
```

See the README’s [State Model](../README.md#state-model) section for conceptual
guidance on premise vs policy usage.

## State Import/Export

### `engine.export_json()`

Export authoritative state as canonical JSON text.

### `engine.import_json(payload)`

Validate and restore authoritative state from exported JSON text.

Use these APIs for authoritative-state transport or persistence only.

Conceptual boundary:

- `export_json()` / `import_json()` transport authoritative state only
- checkpoint APIs transport authoritative state plus resumable continuation state

## Checkpoint APIs

### `engine.export_checkpoint()`

Export a resumable checkpoint object.

### `engine.import_checkpoint(payload)`

Validate and restore a checkpoint object.

### `engine.export_checkpoint_json()`

Export a checkpoint as canonical JSON text.

### `engine.import_checkpoint_json(payload)`

Validate and restore a checkpoint from JSON text.

Use checkpoint APIs when you need both:

- authoritative state
- pending confirmation/continuation state

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

At this boundary, direct key access is expected.

API-level contract notes:

- `pending` is `null` when no continuation is waiting for confirmation
- `pending` captures confirmation-required operations such as replacement flows
- `old_item` may be `null` for `"use_only"` when confirming “use X instead?”
  without an existing exact policy to replace
- imported policy keys are normalized during `import_json(...)` and checkpoint
  authoritative-state restore
- if a policy key normalizes to `""`, the payload is invalid and is rejected
- checkpoint restore is full and deterministic: authoritative state and pending
  continuation are restored together
- checkpoint validation is all-or-nothing; invalid payloads raise and no
  partial restore occurs
- `checkpoint_version` is independent of authoritative state `version` and must
  be bumped when checkpoint contract shape changes, especially `pending`

Typical use cases:

- stateless host or integration boundaries where engine instances are short-lived
- resume after interruption without losing pending clarification flow
- preserve pending confirmation flow state across process or request boundaries

## Controller APIs

These controller APIs are public package exports and can be used directly in
host code, not only through the REPL.

### `step(engine, user_input)`

Run one turn through an engine and return a `StepResult`.

`StepResult` contains:

- `output_version`
- `mode`
- `decision`
- `state`

### `preview(engine, user_input)`

Run a deterministic dry-run preview and return a `PreviewResult`.

`PreviewResult` contains:

- `output_version`
- `mode`
- `decision`
- `state_before`
- `state_after`
- `diff`
- `would_mutate`

`preview(...)` restores live engine state after the dry run.

### `state_diff(state_before, state_after)`

Return a `StructuralDiff` describing premise and policy changes between two
state snapshots.

Typical use:

```python
from context_compiler import (
    create_engine,
    diff_has_changes,
    get_preview_state_after,
    preview,
    state_diff,
)

engine = create_engine()
before = engine.state
dry_run = preview(engine, "prohibit peanuts")
diff = state_diff(before, get_preview_state_after(dry_run))

if diff_has_changes(diff):
    show_preview(diff)
```

Controller helper functions:

- `get_step_decision(step_result)`
- `get_step_state(step_result)`
- `get_preview_decision(preview_result)`
- `get_preview_state_after(preview_result)`
- `preview_would_mutate(preview_result)`
- `diff_has_changes(diff)`

For controller result-envelope details, see the controller conformance fixture
documentation in [tests/fixtures/README.md](../tests/fixtures/README.md).

## Public Constants

Decision-kind constants:

- `DECISION_PASSTHROUGH`
- `DECISION_UPDATE`
- `DECISION_CLARIFY`

Policy-value constants:

- `POLICY_USE`
- `POLICY_PROHIBIT`

Use these when you want explicit string comparisons without hard-coding
literals in host code.

## Result Object Summaries

Public result and data object names exported at package root include:

- `Decision`
- `State`
- `Checkpoint`
- `StepResult`
- `PreviewResult`
- `StructuralDiff`
- `Engine`

These names are part of the public package surface. For the exact portable API
export contract used by tests and ports, see
[tests/fixtures/conformance/api/public-api-v1.json](../tests/fixtures/conformance/api/public-api-v1.json).
