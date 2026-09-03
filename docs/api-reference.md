# API Reference

Public API reference for `context_compiler`.

This page documents the exported package surface and typical usage patterns. It
does not redefine behavioral semantics.

Authoritative behavior documents:

- [Directive Grammar Specification](DirectiveGrammarSpec.md)
- [Architecture boundaries](architecture.md)
- [Project README](../README.md)

For behavioral semantics, use the authoritative documents above. This page
documents the supported public package surface without redefining directive
behavior.

Core boundary:

- core consumes canonical directives
- canonical directive validation remains in core
- semantic validation and authoritative state transitions remain in core
- semantic errors are terminal Decision results for the current input; hosts
  recover only by explicitly selecting and submitting advisory repairs
- human-facing normalization, malformed-input recovery, and intent drafting are
  outside the core contract
- core does not convert failed canonical operations into different directives

## Engine Lifecycle

### `Engine()`

Create a new engine instance.

Typical use:

```python
from context_compiler import Engine

engine = Engine()
```

### `engine.step(user_input)`

Parse one user turn and return a deterministic `Decision`.

Typical use:

```python
decision = engine.step("set premise current project uses uv")
```

Behavior for directive handling and error is
defined by the [Directive Grammar Specification](DirectiveGrammarSpec.md).

`engine.step(...)` is the text-input boundary. It parses one user turn with
`decompose_directive(...)`, returns `no_directive` when the input is not a
canonical directive, and otherwise delegates the accepted canonical directive
to `engine.apply_directive(...)`.

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

- `DirectiveKind`
- `DirectiveSyntaxFailure`
- `DirectiveMetadata`
- `CanonicalDirective`
- `InvalidDirectiveSyntax`
- `get_directive_metadata()`
- `decompose_directive(text)`

Use this surface for exact canonical directive decomposition and
classification via `decompose_directive(...)` only.

Boundary notes:

- `get_directive_metadata()` returns immutable directive metadata derived from
  the internal grammar specs
- each `DirectiveMetadata` exposes only `kind`, `canonical_start`, and
  `operand_names`
- directive metadata is descriptive only; it does not parse text or recognize
  malformed input
- use `decompose_directive(text)` to determine whether text is a complete
  canonical directive
- `decompose_directive(...)` returns `CanonicalDirective` for accepted
  canonical directives
- `decompose_directive(...)` returns `InvalidDirectiveSyntax` for
  directive-shaped input that is not valid canonical syntax
- `decompose_directive(...)` returns `None` when no directive is present
- `CanonicalDirective.kind` uses `DirectiveKind`
- `InvalidDirectiveSyntax.failure` uses `DirectiveSyntaxFailure`
- `InvalidDirectiveSyntax.directive_kind`, when present, uses `DirectiveKind`
- `InvalidDirectiveSyntax.missing_operand`, when present, names the missing
  grammar operand without introducing user-facing message text
- `CanonicalDirective.text` is the canonical serialized directive text derived
  from `kind` and `operands`
- operands are grammar-level text, not normalized semantic values
- `engine.step(...)` remains the authority for error, state
  transitions, and mutation behavior
- `engine.step(...)` is not a general natural-language repair surface; host
  code should send canonical directives when it wants deterministic mutation
- failed replacement requests are not reinterpreted by core into different
  directives
- `use <new> instead of <old>` with an absent `<old>` is a semantic `error`;
  core does not degrade it into plain `use <new>`

`CanonicalDirective.operands` preserves the grammar-recognized operand text.
Core does not lowercase operands, collapse internal operand whitespace, or
convert operand text into engine/domain identifiers at the grammar layer.
`CanonicalDirective.text` is the canonical serialized directive output for that
semantic directive.

Typical metadata use:

```python
from context_compiler.grammar import get_directive_metadata

for metadata in get_directive_metadata():
    print(metadata.kind, metadata.canonical_start, metadata.operand_names)
```

### `engine.apply_directive(directive)`

Apply one already-canonical `CanonicalDirective` to authoritative state.

Typical use:

```python
from context_compiler import Engine
from context_compiler.grammar import CanonicalDirective, decompose_directive

engine = Engine()
directive = decompose_directive("use docker")
assert isinstance(directive, CanonicalDirective)

decision = engine.apply_directive(directive)
```

Boundary notes:

- `apply_directive(...)` does not parse free-form user text
- callers should pass only `CanonicalDirective` values produced or validated by
  the grammar boundary
- semantic validation and authoritative mutation rules are the same whether the
  canonical directive arrives through `step(...)` or `apply_directive(...)`
- `error` remains reserved for canonical directives that fail semantic
  evaluation

### `engine.premise`

Read the current authoritative premise value from a live engine.

### `engine.policies`

Read the current authoritative policy mapping from a live engine.

This property returns a caller-owned copy so callers cannot mutate live engine
state through the returned mapping.

## Decision API

Decisions are ephemeral immutable evaluation results. They are not persisted
and do not provide mapping or serialization behavior.

```python
Decision = NoDirectiveDecision | UpdateDecision | SemanticErrorDecision

class NoDirectiveDecision:
    kind = DecisionKind.NO_DIRECTIVE

class UpdateDecision:
    kind = DecisionKind.UPDATE
    changed: bool

class SemanticErrorDecision:
    kind = DecisionKind.ERROR
    failure: SemanticFailure
    directive: CanonicalDirective
    repairs: tuple[CanonicalDirective, ...]
    message: str  # derived property
```

Use concrete variants with `isinstance` or pattern matching. `Decision.kind`
remains the stable discriminator for generic consumers and cross-language
implementations.

`UpdateDecision.changed` reports whether authoritative state actually changed.
Accepted idempotent directives still return `update`, with `changed=False`.

`SemanticErrorDecision` fields have distinct roles:

- `failure` is the machine-readable semantic failure classification;
- `directive` is the canonical directive rejected by semantic evaluation;
- `repairs` is an ordered tuple of advisory canonical directives;
- `message` is derived human-readable text for presentation.

Callers must use `failure` for control flow rather than parsing `message`.
Repairs are never applied automatically. A host explicitly chooses whether to
submit a repair through `engine.apply_directive(...)`. An empty tuple means no
deterministic repair was proposed.

The normative repair mapping is:

| Failure | Ordered advisory repairs |
| --- | --- |
| `PREMISE_ALREADY_SET` | `change premise to <requested value>` |
| `PREMISE_NOT_SET` | `set premise <requested value>` |
| `ITEM_PROHIBITED` | `remove policy <item>`; `use <item>` |
| `ITEM_ALREADY_IN_USE` | `remove policy <item>`; `prohibit <item>` |
| `REPLACEMENT_TARGET_PROHIBITED` | `remove policy <target>`; retry the original replacement directive |
| `REPLACEMENT_SOURCE_PROHIBITED` | no repair (`()`) |
| `REPLACEMENT_SOURCE_MISSING` | no repair (`()`) |

Repairs are canonical directives, remain ordered, and are advisory only. Hosts
must explicitly select any repair they want to submit; the engine never applies
repairs automatically. `message` is presentation data, not a control-flow
interface.

Return types differ at the two engine boundaries:

- `engine.step(user_input)` returns `NoDirectiveDecision | UpdateDecision |
  SemanticErrorDecision`;
- `engine.apply_directive(directive)` returns `UpdateDecision |
  SemanticErrorDecision` and can never return `NoDirectiveDecision`.

`step(...)` is the raw input boundary: it parses user input, may return
`no_directive` when parsing produces no usable canonical directive, and performs
semantic evaluation only after a `CanonicalDirective` has parsed successfully.
`apply_directive(...)` is the canonical execution boundary and accepts only a
`CanonicalDirective`; it does not parse raw text and returns only `UpdateDecision`
or `SemanticErrorDecision`. Grammar failures are not semantic errors.

Typical use:

```python
from context_compiler import (
    Engine,
    NoDirectiveDecision,
    SemanticErrorDecision,
    UpdateDecision,
)

decision = engine.step(user_input)

if isinstance(decision, SemanticErrorDecision):
    show_to_user(decision.message)
    if decision.repairs:
        offer_repairs(decision.repairs)
elif isinstance(decision, UpdateDecision):
    apply_runtime_rules(changed=decision.changed)
elif isinstance(decision, NoDirectiveDecision):
    handle_as_ordinary_input(user_input)
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
- Decision objects are not part of persisted state; persistence transports
  authoritative premise and policy state only
- imported policy keys are normalized during `import_json(...)`
- if a policy key normalizes to `""`, the payload is invalid and is rejected
- if two imported policy keys normalize to the same canonical key, the payload
  is invalid and is rejected atomically
- if an imported premise sanitizes to `""`, the payload is invalid and is
  rejected atomically

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

Public type alias:

```python
PolicyValue = Literal["use", "prohibit"]
```

`PolicyValue` describes the values returned by `engine.policies`.

## Result Object Summaries

Public result and data object names exported at package root include:

- `Decision`
- `DecisionKind`
- `NoDirectiveDecision`
- `UpdateDecision`
- `SemanticErrorDecision`
- `SemanticFailure`
- `Engine`

These names are part of the public package surface. For the exact portable API
export contract used by tests and ports, see
[tests/fixtures/conformance/api/public-api-v2.json](../tests/fixtures/conformance/api/public-api-v2.json).
