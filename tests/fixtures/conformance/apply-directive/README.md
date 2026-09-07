# Apply-Directive Fixtures

These fixtures define a portable conformance corpus for public
`engine.apply_directive(...)` behavior.

## Contract

Each fixture exercises one canonical directive against authoritative state and
records only portable observations:

* returned `Decision`
* final authoritative state snapshot

This family covers deterministic semantic behavior only. It does not encode
parser internals, monkeypatch behavior, or private helper structure.

## Fixture shape

Each fixture is a JSON object with:

* `id`: stable fixture identifier
* `kind`: always `"apply_directive"`
* `initial_state`: authoritative state before the action
* `prelude`: optional prior public `engine.step(...)` inputs
* `action`: the canonical directive action
* `expected`: the expected decision and final state

### `action`

The portable action forms are:

* `{"fn":"apply_directive","text":"...canonical directive text..."}`
  decomposes the text before applying the resulting directive.
* `{"fn":"apply_directive","directive":{"kind":"...","operands":{...}}}`
  constructs a public `CanonicalDirective` directly and passes it to
  `engine.apply_directive(...)` without parsing text first.

Ports may construct the equivalent canonical directive object using their own
public grammar surface.

## Scope boundary

These fixtures intentionally cover:

* success across representative directive families
* semantic errors preserving state
* replacement behavior
* premise lifecycle
* policy lifecycle

They intentionally do not cover:

* free-form text parsing through `step(...)`
* private helper APIs
* implementation mechanism requirements such as deep-copy strategy
