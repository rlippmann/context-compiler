# Fixture Suites

This directory contains multiple fixture suites with different contracts.

## Fixture types

* [`conformance/`](conformance/) — core engine cross-language conformance contract.
  Includes a small public API presence contract under `conformance/api/`.
* [`engine-regression/structured/`](engine-regression/structured/) — deterministic per-turn engine regression fixtures (including checkpoint snapshots).
* [`preprocessor/`](preprocessor/) — preprocessor heuristic and validation fixtures.

`conformance/` and `engine-regression/structured/` both cover engine behavior at different layers; preprocessor fixtures are intentionally separate from the core engine conformance contract.

## API contract fixture

[`conformance/api/public-api-v1.json`](conformance/api/public-api-v1.json) defines a small public API presence contract for the Python 0.6 surface that ports must expose.

Ports may sync this artifact with conformance fixtures.

Ports should check equivalent public exports and methods using language-appropriate names where casing differs.

Behavioral semantics remain covered by conformance and structured fixtures.

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

## Preprocessor fixtures

[`preprocessor/`](preprocessor/)

These fixtures cover preprocessor behavior (heuristic classification plus output validation), separate from the core engine conformance contract above.

They are exercised by [`tests/test_preprocessor_conformance.py`](../test_preprocessor_conformance.py), including deterministic replay and validation-boundary checks (only validated directive output may pass through).

Portable fixture scope:
- deterministic heuristic and validator input/output contracts intended for cross-language parity
- source-aware parse contract fixtures (`parse_preprocessor_output(raw_output, source_input=...)`) for fallback-boundary parity

Python-local test scope:
- property/fuzz invariants and filesystem/template behaviors (for example `render_prompt` file-loading behavior) remain in Python unit/property tests and are not portable fixture requirements.

Supported `preprocessor/` fixture kinds:

* `heuristic`
  * fields: `input`, `expected`
  * asserts normalized heuristic classification/output
* `validator`
  * fields: `raw_output`, optional `source_input`, `expected`
  * asserts `validate_preprocessor_output(...)` classification/output
* `parse`
  * fields: `raw_output`, optional `source_input`, `expected_parsed`
  * asserts `parse_preprocessor_output(...)` return (`string` or `null`)

They validate:

* heuristic classification determinism
* directive extraction and normalization
* output validation boundaries
* source-aware fallback parse boundaries
* reject/unknown safety handling for ambiguous and near-miss inputs

## Test runner

See [`tests/test_fixtures.py`](../test_fixtures.py) for execution details.
