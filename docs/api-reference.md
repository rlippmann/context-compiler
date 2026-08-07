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

### `create_engine()`

Create a new engine instance.

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
- `match_canonical_directive_start(text, start)`
- `contains_multiple_canonical_directives(text)`
- `decompose_directive(text)`
- `render_directive(kind, /, **operands)`

Use this surface for exact canonical validation, canonical directive syntax
decomposition, or canonical directive string construction only.

Boundary notes:

- `match_canonical_directive_start(...)` only matches a canonical directive
  prefix at a position; it does not validate a whole directive
- `contains_multiple_canonical_directives(...)` detects compound
  directive-shaped structure only; it is not full validation
- use `decompose_directive(text)` to determine whether text is a complete
  canonical directive
- a non-`None` decomposition returns a `CanonicalDirective` with `kind`,
  `operands`, and preserved accepted `text`
- `CanonicalDirective.text` preserves the original accepted input text, so
  caller casing or formatting may remain visible there
- `CanonicalDirective.text` is not canonical serialized directive text
- `match_canonical_directive_start(...)` is only for shallow syntax detection
- operands are grammar-level text, not normalized semantic values
- decomposition returns `None` for any non-canonical input
- `render_directive(...)` produces canonical directive text from semantic kind
  and operands
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
Canonical serialized directive output comes from
`render_directive(kind, /, **operands)`, not from `CanonicalDirective.text`.

### `engine.premise`

Read the current authoritative premise value from a live engine.

### `engine.policies`

Read the current authoritative policy mapping from a live engine.

This property returns a caller-owned copy so callers cannot mutate live engine
state through the returned mapping.

## Decision API

Each user message produces a `Decision`.

```python
class DecisionKind(StrEnum):
    NO_DIRECTIVE = "no_directive"
    UPDATE = "update"
    ERROR = "error"

class Decision(TypedDict):
    kind: DecisionKind
    message: str | None
```

`message` is structurally present on every `Decision`, but only `error`
decisions populate it with meaningful content. `no_directive` and `update`
return `message=None`.

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

`get_error_message(decision)` encodes the semantic convention above: it returns
the user-facing error text only for `error`, otherwise `None`.

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
Use `engine.export_json()` and `engine.import_json()` for persistence and
restoration.

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

## Retired Controller And Audit APIs

The public controller and audit surface was retired for the 0.9 line.

Retired APIs include:

- package-root `step(...)`
- `context_compiler.audit`
- `preview(...)`
- `state_diff(...)`
- result-envelope and accessor helpers tied to those APIs

Current host integrations should call `engine.step(...)` directly, read live
state through `engine.premise` and `engine.policies`, and persist state
through `engine.export_json()` / `engine.import_json()`.

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
- `Engine`

These names are part of the public package surface. For the exact portable API
export contract used by tests and ports, see
[tests/fixtures/conformance/api/public-api-v2.json](../tests/fixtures/conformance/api/public-api-v2.json).
