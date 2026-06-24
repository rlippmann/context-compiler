# Fixture Suites

This directory contains multiple fixture suites with different contracts.

## Fixture types

* [`conformance/`](conformance/) — core engine cross-language conformance contract.
  Includes a small public API presence contract under `conformance/api/`.
* [`engine-regression/structured/`](engine-regression/structured/) — deterministic per-turn engine regression fixtures (including checkpoint snapshots).
`conformance/` and `engine-regression/structured/` both cover engine behavior at different layers.

## API contract fixture

[`conformance/api/public-api-v1.json`](conformance/api/public-api-v1.json) defines a small public API presence contract for the Python 0.7.x surface that ports must expose.

Ports may sync this artifact with conformance fixtures.

Ports should check equivalent public exports and methods using language-appropriate names where casing differs.

Behavioral semantics remain covered by conformance and structured fixtures.

The API presence contract includes the public controller helper accessors:

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

### Prelude

`prelude` simulates prior user inputs to reach states that are not representable via `initial_state` (for example, pending clarification).

## Transcript fixtures

For [`conformance/transcript/`](conformance/transcript/):

Replay messages using `compile_transcript(messages)`.

Results are normalized to:

* `{ "state": ... }`
* `{ "clarify": { "prompt_to_user": ... } }`

## Prompt matching

For conformance transcript fixtures:

* If `prompt_to_user` is a string → exact match
* If `prompt_to_user` is `null` → any non-empty string is accepted

## State JSON fixtures

For [`conformance/state-json/`](conformance/state-json/):

Portable serialization contract coverage for `engine.export_json()` and
`engine.import_json(...)`, including canonical export payload shape and
deterministic validation/error boundaries.

## Checkpoint fixtures

For [`conformance/checkpoint/`](conformance/checkpoint/):

Portable checkpoint import contract coverage for
`engine.import_checkpoint(...)`, including deterministic validation/error
boundaries, atomic failure behavior, and pending-clarification clearing semantics.

## Controller fixtures

For [`conformance/controller/`](conformance/controller/):

Portable controller contract coverage for:

* `step(engine, user_input)` result envelope and state snapshot
* `preview(engine, user_input)` result envelope, `would_mutate`, and non-mutation of live engine state
* `state_diff(state_before, state_after)` deterministic structural diff output

These fixtures keep a minimal, language-neutral contract matrix for controller APIs.
They intentionally validate the raw controller result envelopes; helper accessors
are covered separately by the public API presence contract above.

## Source of truth

Fixtures reflect current Python behavior and tests.
Property/fuzz invariants remain Python-local tests and are not part of the
portable fixture contract.

## Engine regression fixtures

[`engine-regression/structured/`](engine-regression/structured/)

These fixtures capture deterministic per-turn engine behavior, including checkpoint snapshots, and are exercised by [`tests/test_structured_regression.py`](../test_structured_regression.py).

They validate:

* per-turn input handling
* `Decision.kind` outcomes
* clarification prompt behavior
* checkpoint export parity against expected snapshots
* continuation state restoration from checkpoints

## Test runner

See [`tests/test_fixtures.py`](../test_fixtures.py) for execution details.
