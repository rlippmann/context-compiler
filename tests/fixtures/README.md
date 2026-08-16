# Fixture Suites

This directory contains multiple fixture suites with different contracts.

Fixture files in this tree are shared cross-language contract artifacts.
Ports should treat synchronized fixture data as normative for the covered
surface, rather than as Python-only test inputs.

## Fixture types

* [`conformance/`](conformance/) — core engine cross-language conformance contract.
  Includes a small public API presence contract under `conformance/api/`.
* [`engine-regression/structured/`](engine-regression/structured/) — deterministic per-turn engine regression fixtures using authoritative state snapshots.
`conformance/` and `engine-regression/structured/` both cover engine behavior at different layers.

## API contract fixtures

[`conformance/api/public-api-v2.json`](conformance/api/public-api-v2.json) defines the current portable core root public API contract for Python and ports.

Ports may sync this artifact with conformance fixtures.

The contract encodes:

* exact exported `context_compiler.__all__` names
* export kinds (`callable`, `constant`, `type_alias`, `type`, `class`)
* exact public `Engine` members
* stable callable signatures where parameter shape is part of the contract
* forbidden package-root names that must not become public exports
* lightweight deterministic return-shape probes for selected stable helpers

Ports should check equivalent public exports, members, and signatures using language-appropriate names where casing differs.

Behavioral semantics remain covered by conformance and structured fixtures.

## Step fixtures

For [`conformance/step/`](conformance/step/):

Each step fixture runs:

1. optional `prelude` (array of prior user inputs)
2. main `input`

Then asserts:

* returned `Decision`
* final authoritative state snapshot

The `Decision` payload in this family uses one shared shape:

* `{"kind":"no_directive","message":null}`
* `{"kind":"update","message":null}`
* `{"kind":"error","failure": ..., "directive": ..., "repairs": [...], "message": ...}`

Semantic errors always include the machine-readable `failure`, the rejected
canonical `directive`, and an ordered list of advisory canonical `repairs`.
`message` is derived human-readable text for presentation. Non-error outcomes
keep the field for structural consistency and use `null`.

The current runner enforces a closed fixture shape for this family.
Unknown top-level and documented nested fields are rejected.

### Prelude

`prelude` simulates prior user inputs to reach states through the public engine
surface before the main fixture input runs.

Shared `step` fixtures intentionally cover representative engine-observable
parser/no_directive outcomes. Direct grammar classification belongs to the
`conformance/grammar/` fixture family. The step fixtures do not attempt to
freeze every ambiguous natural-language edge case as part of the cross-language
contract.

## Apply-directive fixtures

For [`conformance/apply-directive/`](conformance/apply-directive/):

Portable canonical-directive behavior coverage for `engine.apply_directive(...)`.

Each fixture runs:

1. `initial_state`
2. optional `prelude` through `engine.step(...)`
3. one canonical directive through `engine.apply_directive(...)`

Then asserts:

* returned `Decision`
* final authoritative state snapshot

These fixtures cover representative semantic transitions that are part of the
portable engine contract, including replacement semantics, premise lifecycle,
policy lifecycle, contradiction errors, and idempotent updates.

The current runner enforces a closed fixture shape for this family.
Unknown top-level, action, and documented nested fields are rejected.

## State JSON fixtures

For [`conformance/state-json/`](conformance/state-json/):

Portable serialization contract coverage for `engine.export_json()` and
`engine.import_json(...)`, including canonical export payload shape and
deterministic validation/error boundaries.

The current runner enforces a closed fixture shape for this family.
Unknown top-level, action, and documented expected/error fields are rejected.

## Mutation-isolation fixtures

For [`conformance/mutation-isolation/`](conformance/mutation-isolation/):

Portable authority-isolation fixture definitions for public APIs that return
structured objects or accept caller-owned structured inputs.

These fixtures define declarative scenarios for:

* update `Decision` isolation
* returned decision isolation
* `engine.policies` caller-ownership isolation
* `engine.premise` caller-ownership isolation

The portable contract for this family is:

* no public API return value may provide a mutation path into authoritative engine state
* live semantic reads exposed through public properties must remain caller-owned observations

Legacy mutation-isolation scenarios tied to removed raw-state construction or
raw-state snapshot APIs are not part of the current supported fixture surface.
Authoritative-state setup and round-trip persistence behavior now belongs to the
JSON fixture family, using `engine.import_json(...)` and `engine.export_json()`
as the supported public boundary.

The Python source-of-truth repo executes this fixture family through the
existing conformance runner in
[`tests/test_fixtures.py`](../test_fixtures.py).

Portable fixture data remains language-neutral. Other ports may add execution
support in later synchronized changes.

## Controller fixtures

For [`conformance/controller/`](conformance/controller/):

Portable deterministic workflow fixtures spanning multiple public API calls on a
single engine instance.

These fixtures cover representative controller-level invariants that require
more than one public call, such as:

* repeated `export_json()` / `import_json(...)` fixed-point stability
* `step(...)` / `apply_directive(...)` equivalence for canonical directives
* absence of reserved follow-up state after semantic errors

Each fixture records only portable observations:

* labeled decision or payload observations from public calls
* equality checks between labeled observations
* final authoritative state

The current runner supports:

* `step`
* `apply_directive`
* `export_json`
* `import_json`

## Source of truth

Fixtures reflect current Python behavior and tests.
Property/fuzz invariants remain Python-local tests and are not part of the
portable fixture contract.

For conformance families that enforce identity validation in the shared runner,
the fixture filename stem must match the fixture `id`.

## Engine regression fixtures

[`engine-regression/structured/`](engine-regression/structured/)

These fixtures capture deterministic per-turn engine behavior using
authoritative state snapshots, and are exercised by
[`tests/test_structured_regression.py`](../test_structured_regression.py).

Like the conformance fixture families above, these files are contract artifacts
intended for reuse by other implementations.

They validate:

* per-turn input handling
* `Decision.kind` outcomes
* error prompt behavior
* authoritative state parity against expected snapshots

The current conformance corpus assumes the engine owns authoritative state only.
Clarify results do not reserve later user input or create portable continuation
state.

## Test runner

See [`tests/test_fixtures.py`](../test_fixtures.py) for execution details.
