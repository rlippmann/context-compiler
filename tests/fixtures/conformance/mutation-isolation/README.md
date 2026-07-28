# Mutation-Isolation Fixtures

These fixtures define a portable conformance corpus for mutation isolation and
caller-owned result semantics on the API surface shared by Python and
TypeScript.

## Contract

The contract captured here is **authority isolation**, not immutability.

Returned objects may remain mutable as long as:

* mutating them cannot mutate authoritative engine state
* caller-owned envelopes remain caller-owned
* helper accessors preserve or avoid identity only where the public contract
  says they should

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

* `create_engine`
* `engine.state`
* `engine.step`
* `controller.step`
* `controller.preview`
* helper accessors such as `get_decision_state`, `get_step_state`, and
  `get_preview_state_after`

### `handles`

`handles` names the caller-owned object graph exposed by the operation.

Examples:

* constructor argument object
* returned state snapshot
* returned `Decision`
* returned controller result envelope
* helper return value

### `mutations`

Each mutation describes:

* `target_handle`: which caller-owned object to mutate
* `path`: key path within that object
* `op`: currently `"set"`
* `value`: replacement value

The mutation language stays language-neutral and avoids embedding Python or
TypeScript syntax into the fixtures.

### `expected`

`expected` captures only observable behavior:

* `authoritative_state`: engine state expected after caller-side mutation
* `preview_live_state_unchanged`: whether preview must still leave live engine
  state unchanged
* `identity_assertions`: optional identity expectations between handles and
  nested envelope members
* `caller_owned_observations`: optional value observations within caller-owned
  envelopes after mutation

## Scope boundary

These fixtures cover only the shared API surface for Python 0.9 and the
unsynchronized TypeScript port.

They intentionally do **not** include:

* checkpoint APIs
* pending-continuation APIs
* obsolete TypeScript-only authority surfaces
* implementation-mechanism requirements such as `deepcopy`, frozen objects, or
  `readonly`
