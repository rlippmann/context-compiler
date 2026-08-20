# Mutation-Isolation Fixtures

These fixtures define a portable conformance corpus for mutation isolation and
caller-owned result semantics on the API surface shared by Python and
TypeScript.

## Contract

The contract captured here is authority isolation plus the covered public
mutation behavior of exposed grammar objects.

Returned objects may remain mutable as long as:

* mutating them cannot mutate authoritative engine state
* caller-owned envelopes remain caller-owned
* helper accessors preserve or avoid identity only where the public contract
  says they should

For the grammar-object fixtures, exposed `CanonicalDirective.operands` and the
covered `DirectiveMetadata` fields must preserve mutation isolation: a caller
mutation either is rejected or does not change the exposed value observed after
the mutation.

## Fixture shape

Each fixture is a JSON object with:

* `id`: stable fixture identifier
* `kind`: always `"mutation_isolation"`
* `initial_state`: authoritative engine state before any operation
* `operation`: the public API action that produces or accepts a structured
  object
* `handles`: named caller-owned objects or nested members exposed by the
  operation
* `mutations`: declarative mutations applied to caller-owned handles
* `expected`: authoritative-state and ownership observations after mutation

### `operation`

`operation` identifies the shared API boundary under test and any inputs needed
to reach it.

Examples:

* `engine.step`
* `engine.policies`
* `engine.premise`
* `canonical_directive.operands`
* `directive_metadata`
For the current corpus, `operation` uses a closed per-function field set.
Unknown operation fields are invalid.

### `handles`

`handles` names the caller-owned object graph exposed by the operation.

Examples:

* constructor argument object
* returned state snapshot
* returned `Decision`
`handle.kind` is a closed descriptive metadata set used for fixture validation.
It documents expected ownership roles but does not currently change execution.

### `mutations`

Each mutation describes:

* `target_handle`: which caller-owned object to mutate
* `path`: key path within that object
* `op`: currently `"set"`
* `value`: replacement value

The mutation language stays language-neutral and avoids embedding Python or
TypeScript syntax into the fixtures.

The mutation language supports string-key dict or mapping paths and public
attribute paths. List traversal is outside the scope of this fixture family for
now.

### `expected`

`expected` captures only observable behavior:

* `authoritative_state`: engine state expected after caller-side mutation
* `caller_owned_observations`: optional value observations within caller-owned
  objects after mutation

## Scope boundary

These fixtures cover only the shared API surface for Python 0.9 and the
unsynchronized TypeScript port.

They intentionally do **not** include:

* checkpoint APIs
* removed continuation-state APIs
* obsolete TypeScript-only authority surfaces
* implementation-mechanism requirements such as `deepcopy`, frozen objects, or
  `readonly`
