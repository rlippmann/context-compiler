# Conformance Fixtures

These fixtures define the cross-language conformance contract for the Context Compiler.

## Layout

[`conformance/`](conformance/)

* [`step/`](conformance/step/)
* [`transcript/`](conformance/transcript/)

## Step fixtures

Each step fixture runs:

1. optional `prelude` (array of prior user inputs)
2. main `input`

Then asserts:

* returned `Decision`
* final `engine.state`

### Prelude

`prelude` simulates prior user inputs to reach states that are not representable via `initial_state` (for example, pending clarification).

## Transcript fixtures

Replay messages using `compile_transcript(messages)`.

Results are normalized to:

* `{ "state": ... }`
* `{ "clarify": { "prompt_to_user": ... } }`

## Prompt matching

* If `prompt_to_user` is a string → exact match
* If `prompt_to_user` is `null` → any non-empty string is accepted

## Source of truth

Fixtures reflect current Python behavior and tests.

## Test runner

See [`tests/test_fixtures.py`](../test_fixtures.py) for execution details.
