# Structured Regression Fixtures

These fixtures define deterministic, per-turn behavioral regression coverage for the Python engine.

## Layout

* `scenarios/`: input stimuli and optional setup (`initial_checkpoint`)
* `expected/`: exact per-turn expected outputs

Each scenario file in `scenarios/` must have a matching file in `expected/` with the same `id`.

## Turn Result Schema

Each expected turn uses:

* `input`
* `decision.kind`
* `decision.prompt_to_user`
* `checkpoint`

`decision.state` is intentionally omitted because `checkpoint` is the authoritative resumable artifact.

## Why Checkpoint Every Turn

A full checkpoint is stored and compared on every turn so regressions are visible in:

* authoritative state
* pending continuation state

## Prompt Matching

`decision.prompt_to_user` is matched exactly, including clarify text.

## Adding a Scenario

1. Add a scenario input file under `scenarios/`.
2. Add the matching expected per-turn golden file under `expected/`.
3. Keep files JSON-only, deterministic, and easy to diff.

### Scope Boundary

These fixtures validate **deterministic engine behavior only**:

- `engine.step(...)` outputs (`Decision.kind`, `prompt_to_user`)
- post-turn checkpoint (`authoritative_state` + `pending`)

They do **not** cover:

- REPL / user-facing formatting
- LLM integration behavior
- precompiler / heuristic directive generation

These surfaces are tested separately because:

- REPL output may intentionally differ from the underlying state representation
- precompiler behavior is non-deterministic and outside the engine contract

This fixture set is the **canonical engine-level conformance surface**, and may be reused by other implementations (e.g., TypeScript) to validate identical engine behavior.
