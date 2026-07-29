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

## API contract fixture

[`conformance/api/public-api-v1.json`](conformance/api/public-api-v1.json) defines the current portable core public API contract for Python and ports.

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

The API contract includes the public controller helper accessors:

* `get_step_decision`
* `get_step_state`
* `get_preview_decision`
* `get_preview_state_after`
* `preview_would_mutate`
* `diff_has_changes`

## Step fixtures

For [`conformance/step/`](conformance/step/):

Each step fixture runs:

1. optional `prelude` (array of prior user inputs)
2. main `input`

Then asserts:

* returned `Decision`
* final `engine.state`

The current runner enforces a closed fixture shape for this family.
Unknown top-level and documented nested fields are rejected.

### Prelude

`prelude` simulates prior user inputs to reach states that are not representable
via `initial_state` (for example, runtime-only semantic continuation when the
active engine contract supports it).

Shared `step` fixtures intentionally cover representative parser and passthrough
boundaries. They do not attempt to freeze every ambiguous natural-language edge
case as part of the cross-language contract.

## State JSON fixtures

For [`conformance/state-json/`](conformance/state-json/):

Portable serialization contract coverage for `engine.export_json()` and
`engine.import_json(...)`, including canonical export payload shape and
deterministic validation/error boundaries.

The current runner enforces a closed fixture shape for this family.
Unknown top-level, action, and documented expected/error fields are rejected.

## Controller fixtures

For [`conformance/controller/`](conformance/controller/):

Portable controller contract coverage for:

* `step(engine, user_input)` result envelope and state snapshot
* `preview(engine, user_input)` result envelope, `would_mutate`, and non-mutation of live engine state
* `state_diff(state_before, state_after)` deterministic structural diff output

These fixtures keep a minimal, language-neutral contract matrix for controller APIs.
They intentionally validate the raw controller result envelopes; helper accessors
are covered separately by the public API presence contract above.

The current runner enforces a closed fixture shape for this family.
Unknown top-level, action, expected, and documented result/diff fields are rejected.

## Mutation-isolation fixtures

For [`conformance/mutation-isolation/`](conformance/mutation-isolation/):

Portable authority-isolation fixture definitions for public APIs that return
structured objects or accept caller-owned structured inputs.

These fixtures define declarative scenarios for:

* constructor input isolation
* `engine.state` snapshot isolation
* update `Decision.state` isolation
* controller result isolation
* preview result isolation
* helper accessor ownership and identity semantics

The portable contract for this family is:

* no public API return value may provide a mutation path into authoritative engine state
* no caller-supplied input may remain aliased into authoritative engine state
* helper accessors may return caller-owned nested members by identity when that
  behavior is intentional and documented

The Python source-of-truth repo executes this fixture family through the
existing conformance runner in
[`tests/test_fixtures.py`](../test_fixtures.py).

Portable fixture data remains language-neutral. Other ports may add execution
support in later synchronized changes.

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
* clarification prompt behavior
* authoritative state parity against expected snapshots

If a future engine contract restores supported continuation behavior,
planned conformance coverage should include:

* incomplete directives do not create pending continuation
* compound directives do not create pending continuation
* malformed replacement syntax does not create pending continuation
* valid canonical directives that clarify without pending continuation
* valid canonical directives that clarify and create pending continuation
* deterministic `yes` resolution of the exact blocked transition
* deterministic `no` rejection that clears pending continuation
* deterministic handling of unrelated input while pending

## Test runner

See [`tests/test_fixtures.py`](../test_fixtures.py) for execution details.
