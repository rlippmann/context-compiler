# API Reference

This page documents the public Python API exported by `context_compiler`.
For exact directive syntax and core behavior, see the
[Directive Grammar Specification](DirectiveGrammarSpec.md). For system
responsibilities and boundaries, see [architecture.md](architecture.md).

## Engine

### Engine()

Create an engine with empty premise and policy state.

```python
from context_compiler import Engine

engine = Engine()
```

### engine.step(user_input: str) -> Decision

Accept raw user input and return one of:

- [`NoDirectiveDecision`](#nodirectivedecision) when the input does not match a supported directive;
- [`UpdateDecision`](#updatedecision) when a supported directive is accepted;
- [`SemanticErrorDecision`](#semanticerrordecision) when a supported directive conflicts with current state.

```python
result = engine.step("use docker")
```

### engine.apply_directive(directive: CanonicalDirective) -> UpdateDecision | SemanticErrorDecision

Apply a parsed [`CanonicalDirective`](#canonicaldirective), not raw text.

```python
from context_compiler.grammar import CanonicalDirective, decompose_directive

directive = decompose_directive("use docker")
assert isinstance(directive, CanonicalDirective)
result = engine.apply_directive(directive)
```

### engine.premise: str | None

Return the current premise.

### engine.policies: Mapping[str, PolicyValue]

Return a defensive copy of the current policy mapping. Changes to the returned
mapping do not change the engine. Values use [`PolicyValue`](#policyvalue).

### engine.export_json() -> str

Return the current premise and policies as canonical JSON text.

### engine.import_json(payload: str) -> None

Accept exported JSON text and replace the engine’s current state. Invalid or
unsupported state payloads raise `ValueError`.

```python
saved = engine.export_json()
restored = Engine()
restored.import_json(saved)
```

## Decisions

### Decision

The type alias for the three results returned by `Engine.step(...)`:

```python
Decision = NoDirectiveDecision | UpdateDecision | SemanticErrorDecision
```

`Engine.apply_directive(...)` returns only `UpdateDecision | SemanticErrorDecision`;
it never returns `NoDirectiveDecision`.

### DecisionKind

The stable discriminator for a [`Decision`](#decision):

| Member | Value |
| --- | --- |
| `NO_DIRECTIVE` | `"no_directive"` |
| `UPDATE` | `"update"` |
| `ERROR` | `"error"` |

### NoDirectiveDecision

An empty result for input that does not match a supported directive.
Its kind is `DecisionKind.NO_DIRECTIVE`.

### UpdateDecision

An accepted directive result.

#### UpdateDecision.changed: bool

Whether engine state changed.

An accepted idempotent directive still returns [`UpdateDecision`](#updatedecision) with
`changed=False`.

### SemanticErrorDecision

A rejected directive result with:

#### SemanticErrorDecision.failure: SemanticFailure

The machine-readable failure category.

#### SemanticErrorDecision.directive: CanonicalDirective

The rejected directive.

#### SemanticErrorDecision.repairs: tuple[CanonicalDirective, ...]

Ordered advisory repairs.

#### SemanticErrorDecision.message: str

Human-readable presentation text.

Repairs are never applied automatically. A caller may explicitly submit a
selected repair through `engine.apply_directive(...)`. An empty tuple means no
repair was proposed. Use `failure` for program logic rather than parsing
`message`.

### SemanticFailure

The failure categories used by [`SemanticErrorDecision`](#semanticerrordecision):

| Member | Value |
| --- | --- |
| `PREMISE_ALREADY_SET` | `"premise_already_set"` |
| `PREMISE_NOT_SET` | `"premise_not_set"` |
| `ITEM_PROHIBITED` | `"item_prohibited"` |
| `ITEM_ALREADY_IN_USE` | `"item_already_in_use"` |
| `REPLACEMENT_SOURCE_PROHIBITED` | `"replacement_source_prohibited"` |
| `REPLACEMENT_TARGET_PROHIBITED` | `"replacement_target_prohibited"` |
| `REPLACEMENT_SOURCE_MISSING` | `"replacement_source_missing"` |

The repair mapping is:

| Failure | Ordered advisory repairs |
| --- | --- |
| `PREMISE_ALREADY_SET` | `change premise to <requested value>` |
| `PREMISE_NOT_SET` | `set premise <requested value>` |
| `ITEM_PROHIBITED` | `remove policy <item>`; `use <item>` |
| `ITEM_ALREADY_IN_USE` | `remove policy <item>`; `prohibit <item>` |
| `REPLACEMENT_TARGET_PROHIBITED` | `remove policy <target>`; retry the original replacement |
| `REPLACEMENT_SOURCE_PROHIBITED` | no repair |
| `REPLACEMENT_SOURCE_MISSING` | no repair |

## Grammar

The public grammar API is available from `context_compiler.grammar`.

### DirectiveKind

The supported directive families:

- `SET_PREMISE`
- `CHANGE_PREMISE`
- `USE_ITEM`
- `PROHIBIT_ITEM`
- `REMOVE_POLICY`
- `REPLACE_USE`
- `CLEAR_PREMISE`
- `RESET_POLICIES`
- `CLEAR_STATE`

### DirectiveSyntaxFailure

The directive-shaped syntax failure categories:

- `COMPOUND_DIRECTIVE`
- `MISSING_REQUIRED_OPERAND`
- `MALFORMED_DIRECTIVE`

### DirectiveMetadata

Describes one directive family with these public fields:

#### DirectiveMetadata.kind: DirectiveKind

The directive family.

#### DirectiveMetadata.canonical_start: str

The directive’s canonical starting text.

#### DirectiveMetadata.operand_names: tuple[str, ...]

The names of its operands.

### CanonicalDirective

Represents one parsed directive.

#### CanonicalDirective.kind: DirectiveKind

The directive family.

#### CanonicalDirective.operands: Mapping[str, str]

The named operand text.

#### CanonicalDirective.text: str

The serialized directive text.

The recognized operand text is preserved. `text` is derived from `kind` and
`operands`.

### InvalidDirectiveSyntax

Describes directive-shaped input that does not match supported syntax:

#### InvalidDirectiveSyntax.failure: DirectiveSyntaxFailure

The syntax failure category.

#### InvalidDirectiveSyntax.directive_kind: DirectiveKind | None

The directive family, when identified.

#### InvalidDirectiveSyntax.missing_operand: str | None

The missing operand name, when identified.

### decompose_directive(text: str) -> CanonicalDirective | InvalidDirectiveSyntax | None

Accept a string and return one of:

- [`CanonicalDirective`](#canonicaldirective) for supported syntax;
- [`InvalidDirectiveSyntax`](#invaliddirectivesyntax) for directive-shaped input with invalid syntax;
- `None` when no directive is present.

```python
from context_compiler.grammar import CanonicalDirective, decompose_directive

result = decompose_directive("use docker")
assert isinstance(result, CanonicalDirective)
print(result.text)  # use docker
```

### get_directive_metadata() -> tuple[DirectiveMetadata, ...]

Return a tuple of [`DirectiveMetadata`](#directivemetadata) values for the
supported directive families.

```python
from context_compiler.grammar import get_directive_metadata

for metadata in get_directive_metadata():
    print(metadata.kind, metadata.canonical_start, metadata.operand_names)
```

## Constants and types

Decision-kind constants:

- `DECISION_NO_DIRECTIVE = "no_directive"`
- `DECISION_UPDATE = "update"`
- `DECISION_ERROR = "error"`

Policy-value constants:

- `POLICY_USE = "use"`
- `POLICY_PROHIBIT = "prohibit"`

### PolicyValue

The type alias `Literal["use", "prohibit"]`.

## Migration note

The controller, preview, audit, checkpoint, and package-root `step(...)`
surfaces were retired in 0.9. Use `Engine` and its public properties and
persistence methods instead. The
[public API conformance fixture](../tests/fixtures/conformance/api/public-api-v2.json)
records the supported package-root surface.
