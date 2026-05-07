# Fixture Suites

This directory contains multiple fixture suites with different contracts.

## Fixture types

* [`conformance/`](conformance/) — core engine cross-language conformance contract.
* [`preprocessor/`](preprocessor/) — preprocessor heuristic and validation fixtures.

Preprocessor fixtures are intentionally separate from the core engine conformance contract.

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

## Preprocessor fixtures

[`preprocessor/`](preprocessor/)

These fixtures cover preprocessor behavior (heuristic classification plus output validation), separate from the core engine conformance contract above.

They are exercised by [`tests/test_preprocessor_conformance.py`](../test_preprocessor_conformance.py), including deterministic replay and validation-boundary checks (only validated directive output may pass through).

## Test runner

See [`tests/test_fixtures.py`](../test_fixtures.py) for execution details.
