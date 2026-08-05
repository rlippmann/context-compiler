# Structured Regression Fixtures

These fixtures define deterministic, per-turn behavioral regression coverage for the Python engine.

## Layout

* `scenarios/`: input stimuli and optional setup (`initial_state`)
* `expected/`: exact per-turn expected outputs

Each scenario file in `scenarios/` must have a matching file in `expected/`
with the same `id`.

Identity rules:

* scenario filename stem must match scenario `id`
* expected filename stem must match expected `id`
* scenario `id` and expected `id` must match

Scenario metadata is intentionally small:

* `inputs` is required
* `initial_state` is optional setup metadata
* `description` is optional descriptive metadata

## Turn Result Schema

Each expected turn uses:

* `input`
* `decision.kind`
* `decision.message`
* `state`

State is intentionally stored separately in each turn artifact rather than on
the `Decision`.
`decision.message` is only semantically meaningful for `error`; non-error turns
store `null` for structural consistency.

## Why Store State Every Turn

A full authoritative state snapshot is stored and compared on every turn so
regressions are visible in:

* authoritative state

## Prompt Matching

`decision.message` is matched exactly, including `null` for non-error turns.

## Adding a Scenario

1. Add a scenario input file under `scenarios/`.
2. Add the matching expected per-turn golden file under `expected/`.
3. Keep filenames aligned with each file's `id`.
4. Keep files JSON-only, deterministic, and easy to diff.

### Scope Boundary

These fixtures validate **deterministic engine behavior only**:

* `engine.step(...)` outputs (`Decision.kind`, `Decision.message`)
* post-turn authoritative state snapshot

They do **not** cover:

* REPL / user-facing formatting
* LLM integration behavior
* acquisition-layer directive drafting

These surfaces are tested separately because:

* REPL output may intentionally differ from the underlying state representation
* acquisition-layer drafting is outside the engine contract

This fixture set is the **canonical engine-level conformance surface**, and may be reused by other implementations (e.g., TypeScript) to validate identical engine behavior.

## Fixture Policy

These fixtures are contract artifacts. Changes should be intentional and reviewed.

If deterministic engine behavior changes, update the corresponding `engine-regression/structured` fixtures in the same PR and explain the behavioral contract change.

Fixture regeneration must be explicit and opt-in. Normal test runs are read-only and must fail on mismatches rather than rewriting fixtures.
