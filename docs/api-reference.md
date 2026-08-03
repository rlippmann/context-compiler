# API Reference

Public API reference for `context_compiler`.

This page documents the exported package surface and typical usage patterns. It
does not redefine behavioral semantics.

Authoritative behavior documents:

- [Directive Grammar Specification](DirectiveGrammarSpec.md)
- [Architecture boundaries](architecture.md)
- [Project README](../README.md)

For behavioral semantics, use the authoritative documents above. This page
documents the supported public package surface without redefining directive or
continuation behavior.

Core boundary:

- core consumes canonical directives
- canonical directive validation remains in core
- semantic validation and authoritative state transitions remain in core
- pending continuation, when supported, is created only by semantic evaluation
  of canonical directives
- human-facing normalization, malformed-input recovery, and intent drafting are
  outside the core contract
- core does not convert failed canonical operations into different directives

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

Behavior for directive handling and error is
defined by the [Directive Grammar Specification](DirectiveGrammarSpec.md).

Important grammar contract:

- one input may contain at most one canonical directive
- directive-shaped invalid input is outside the canonical language
- `error` is reserved for canonical directives that fail semantic evaluation
- quote characters do not create protected literal regions inside recognized
  directive payloads

### `context_compiler.grammar`

Canonical grammar helpers are available from the `context_compiler.grammar`
submodule.

Public grammar surface:

- `CanonicalDirective`
- `DirectiveKind`
- `ValidatedDirective`
- `decompose_directive(text)`
- `validate_directive(text)`
- `is_canonical_directive(text)`
- `render_directive(kind, /, **operands)`

Use this surface for exact canonical validation, canonical directive syntax
decomposition, or canonical directive string construction only.

Boundary notes:

- decomposition exposes canonical syntax only
- operands are grammar-level text, not normalized semantic values
- validation returns `None` for any non-canonical input
- decomposition returns `None` for any non-canonical input
- rendering is syntax-only and performs no state interpretation
- `engine.step(...)` remains the authority for error, state
  transitions, and mutation behavior
- `engine.step(...)` is not a general natural-language repair surface; host
  code should send canonical directives when it wants deterministic mutation
- failed replacement requests are not reinterpreted by core into different
  directives
- `use <new> instead of <old>` with an absent `<old>` is not a pending or
  error-only runtime category; it follows the deterministic semantic
  rules defined in the specification

`CanonicalDirective.operands` preserves the grammar-recognized operand text.
Core does not lowercase operands, collapse internal operand whitespace, or
convert operand text into engine/domain identifiers at the grammar layer.

### `engine.state`

Read the current authoritative in-memory state snapshot.

Use this when you need the full authoritative state snapshot, such as
serialization, persistence, or snapshot-based host logic.

### `engine.premise`

Read the current authoritative premise value from a live engine.

### `engine.policies`

Read the current authoritative policy mapping from a live engine.

This property returns a caller-owned copy so callers cannot mutate live engine
state through the returned mapping.

## Decision API

Each user message produces a `Decision`.

```python
class NoDirectiveDecision(TypedDict):
    kind: Literal["no_directive"]

class UpdateDecision(TypedDict):
    kind: Literal["update"]
    state: State

class ErrorDecision(TypedDict):
    kind: Literal["error"]
    message: str

Decision = NoDirectiveDecision | UpdateDecision | ErrorDecision
```

Decision kinds:

| kind | Intended host use |
| --- | --- |
| `no_directive` | no canonical directive recognized; no authoritative state change; host decides what to do next |
| `update` | authoritative state changed; host may apply downstream behavior using updated state |
| `error` | show `message`; do not continue normal downstream processing yet |

Helper functions:

- `is_no_directive(decision)`
- `is_update(decision)`
- `is_error(decision)`
- `get_error_message(decision)`
- `get_decision_state(decision)`

Typical use:

```python
from context_compiler import is_error, is_update

decision = engine.step(user_input)

if is_error(decision):
    show_to_user(decision["message"])
elif is_update(decision):
    apply_runtime_rules()
```

## State Access

Use `engine.premise` and `engine.policies` for live engine-owned reads.
Use `engine.state` when you need the full authoritative snapshot.

Typical use:

```python
blocked_tools = sorted(
    item for item, value in engine.policies.items() if value == "prohibit"
)
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

- `export_json()` / `import_json()` are the current persistence contract
- pending continuation, when supported by the engine contract, is runtime state
  rather than a documented persistence feature
- imported policy keys are normalized during `import_json(...)`
- if a policy key normalizes to `""`, the payload is invalid and is rejected

## Controller And Audit APIs

The `step(...)` convenience wrapper remains part of the root host-facing API.

Preview and structural diff helpers live under `context_compiler.audit`.

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
from context_compiler import create_engine
from context_compiler.audit import (
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

Audit helper functions:

- `get_step_decision(step_result)`
- `get_step_state(step_result)`
- `get_preview_decision(preview_result)`
- `get_preview_state_after(preview_result)`
- `preview_would_mutate(preview_result)`
- `diff_has_changes(diff)`

For audit result-envelope details, see the fixture
documentation in [tests/fixtures/README.md](../tests/fixtures/README.md).

## Public Constants

Decision-kind constants:

- `DECISION_NO_DIRECTIVE`
- `DECISION_UPDATE`
- `DECISION_ERROR`

Policy-value constants:

- `POLICY_USE`
- `POLICY_PROHIBIT`

Use these when you want explicit string comparisons without hard-coding
literals in host code.

## Result Object Summaries

Public result and data object names exported at package root include:

- `Decision`
- `State`
- `StepResult`
- `Engine`

These names are part of the public package surface. For the exact portable API
export contract used by tests and ports, see
[tests/fixtures/conformance/api/public-api-v2.json](../tests/fixtures/conformance/api/public-api-v2.json).
