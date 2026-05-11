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

## Source of truth

Fixtures reflect current Python behavior and tests.

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

Python-local test scope:
- property/fuzz invariants and filesystem/template behaviors (for example `render_prompt` file-loading behavior) remain in Python unit/property tests and are not portable fixture requirements.

They validate:

* heuristic classification determinism
* directive extraction and normalization
* output validation boundaries
* reject/unknown safety handling for ambiguous and near-miss inputs

## Test runner

See [`tests/test_fixtures.py`](../test_fixtures.py) for execution details.
