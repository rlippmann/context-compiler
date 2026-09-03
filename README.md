# Context Compiler

[![PyPI version](https://img.shields.io/pypi/v/context-compiler)](https://pypi.org/project/context-compiler/)
[![Python versions](https://img.shields.io/pypi/pyversions/context-compiler)](https://pypi.org/project/context-compiler/)
[![License](https://img.shields.io/pypi/l/context-compiler)](https://pypi.org/project/context-compiler/)
[![codecov](https://codecov.io/gh/rlippmann/context-compiler/branch/main/graph/badge.svg)](https://codecov.io/gh/rlippmann/context-compiler)

Context Compiler is a deterministic conversational state authority for LLM applications.
It handles canonical directive execution, semantic validation, terminal error
decisions, advisory repairs, and structured authoritative state for the host.

## What Context Compiler provides

Context Compiler gives hosts fixed state rules:

- handle canonical explicit state changes with deterministic rules
- error instead of silent overwrite for blocked/ambiguous changes
- return structured terminal errors with explicitly selectable advisory repairs
- export and import authoritative state for host-managed persistence
- produce structured authoritative state for downstream host decisions

The model generates responses. The compiler owns state.
Human-facing normalization, malformed-input recovery, and intent drafting belong
outside core.

## How the compiler metaphor works

Like a compiler, it parses canonical directives, validates them, applies fixed rules, and
produces a stable result the host can use. It treats important instructions as
structured state instead of temporary prompt text. It is not source-code
compilation, not a reasoning model, and not a natural-language repair layer.

## 10-Second Example

User sets a premise once:

```text
User: set premise current project uses uv
```

Outcome: premise state includes `"current project uses uv"`.

Later in the conversation:

```text
User: how should I run the tests?
```

Your host sends the saved authoritative state with this later request, so the
model answers in the context of the saved premise (`current project uses uv`)
instead of relying on memory of earlier conversation text.

---

## Deterministic behavior (examples)

Context Compiler makes state-change rules explicit so behavior stays repeatable.

The architecture has three layers:

- syntax classification decides whether input is a canonical directive, invalid
  directive-shaped syntax, or ordinary no_directive
- semantic evaluation decides whether a canonical directive updates state,
  clarifies, or no-ops
- semantic evaluation returns an update or a terminal error with structured
  advisory repairs when a canonical directive conflicts with state

### Explicit directive

```text
set premise project deadline is Friday
```

- Base model: silently accepts / rewrites
- Context Compiler: applies a repeatable state update

### Compound directive rejection

```text
use docker and prohibit peanuts
```

- Without an authority layer: host/model behavior varies
- Context Compiler: treats this as invalid directive-shaped syntax and keeps authoritative state unchanged

### State-dependent operation

```text
clear state
use podman instead of docker
```

- Without explicit state transition rules: behavior depends on host/model handling
- Context Compiler: applies the deterministic resulting transition when
  `docker` is present and `use podman` is otherwise valid; other semantic
  conflicts may still error

### Lifecycle enforcement

```text
clear state
change premise to project deadline is Thursday
```

- Without explicit transition checks: behavior depends on host/model handling
- Context Compiler: asks for error and keeps saved state unchanged

---

## Architecture

```text
User Input
     │
     ▼
Context Compiler
     │
     ▼
Decision
     │
     ▼
Host Application
 ├─ error → ask user
 ├─ no_directive → no canonical directive recognized; host decides what to do next
 └─ update → authoritative state mutated; host may use compiled state downstream
```

The compiler never calls the LLM. Your app decides what to do with the returned
`Decision`.

---

## Quickstart

Use Context Compiler in your host application first:

```python
from context_compiler import (
    Engine,
    NoDirectiveDecision,
    SemanticErrorDecision,
    UpdateDecision,
)

engine = Engine()

user_input = "set premise current project uses uv"
decision = engine.step(user_input)

if isinstance(decision, SemanticErrorDecision):
    show_to_user(decision.message)
elif isinstance(decision, UpdateDecision):
    messages = build_messages(
        premise=engine.premise,
        policies=engine.policies,
        user_input=user_input,
    )
    render(call_llm(messages))
elif isinstance(decision, NoDirectiveDecision):
    render(call_llm(user_input))
```

This is the main integration path: your app owns the model call and uses the
compiler as the authority layer for state transitions.

For runnable application-layer examples, see
[`context-compiler-example-integrations`](https://github.com/rlippmann/context-compiler-example-integrations).
That companion repository shows enforcement points built on compiler state,
including retrieval filtering, schema selection, tool gating, execution
authorization, gateway middleware, runtime state handling, and prompt
construction.

## Does it Work?

Yes. The current demo suite in this repository contains 7 scored demos
(`01`-`05`, `07`, `08`) plus 1 informational demo (`06`).

The published verification matrix records 7 model runs from an earlier
8-scored-demo runner across hosted/frontier providers and local Ollama models.
In those published runs,
baseline passed **24 / 56**, reinjected-state passed **40 / 56**, and both
compiler paths passed **56 / 56**.

→ [Current demo set and output modes](demos/README.md)
Current and historical published results: [docs/demos-results.md](docs/demos-results.md)

## Interactive Playground

Use the REPL to explore behavior, learn the directive grammar, and debug or
test host-side state rules.

```bash
pip install context-compiler
context-compiler
```

Preload options load authoritative state:

- `--initial-state-json` / `--initial-state-file` load saved state
  (via exported state JSON).

REPL commands (not engine directives):

- `state` shows current saved state.
- `step <input>` is an explicit alias of normal bare-input step behavior.

Bare REPL input behavior remains unchanged.

## Machine-Readable CLI Usage

Use `--json` when you want one complete JSON object per processed input line
for non-interactive usage.

```bash
context-compiler --json < input.txt
```

The JSON output uses `output_version: 2`. Decision payloads expose structured
fields: updates include `changed`; semantic errors include `failure`, the
failed canonical `directive`, ordered advisory `repairs`, and `message`.
These fields are a CLI projection of ephemeral Decisions, not Decision object
serialization. Repairs are never applied automatically.

Preload options load authoritative state:

- `--initial-state-json` / `--initial-state-file` load saved state
  (via exported state JSON).

## Installation

Requirements:

- Python 3.11+

Install:

```bash
pip install context-compiler
```

Packaging notes:

- Base install includes the core authority-layer engine and CLI.
- Example and demo source files are available in the repository and source distribution.
- To run the demos from this repository, clone the repo and install `context-compiler[demos]`.
- The `[demos]` extra installs optional dependencies such as LiteLLM. It does not install demo source files into site-packages.

### Development

```bash
uv sync --dev
uv run pytest
```

CI enforces 100% coverage for the core `src/context_compiler` package. The
coverage badge represents that authoritative core-package target, not the
entire repository.

## Decision API

Each user message produces one immutable `Decision` variant. Use concrete
variants with `isinstance` or pattern matching; use `kind` when generic code
needs the stable discriminator.

```python
class DecisionKind(StrEnum):
    NO_DIRECTIVE = "no_directive"
    UPDATE = "update"
    ERROR = "error"

Decision = NoDirectiveDecision | UpdateDecision | SemanticErrorDecision

@dataclass(frozen=True, slots=True)
class NoDirectiveDecision:
    kind = DecisionKind.NO_DIRECTIVE

@dataclass(frozen=True, slots=True)
class UpdateDecision:
    kind = DecisionKind.UPDATE
    changed: bool

@dataclass(frozen=True, slots=True)
class SemanticErrorDecision:
    kind = DecisionKind.ERROR
    failure: SemanticFailure
    directive: CanonicalDirective
    repairs: tuple[CanonicalDirective, ...]
    message: str
```

`UpdateDecision.changed` reports whether authoritative state actually changed.
An accepted idempotent directive is still an `update` with
`changed=False`.

`SemanticErrorDecision.message` is derived human-readable text. Callers should
use `failure` for machine decisions rather than parsing the message.

`directive` is the canonical directive that failed semantic evaluation.
`repairs` is an ordered tuple of advisory canonical directives. Repairs are
never applied automatically; a host must explicitly submit a selected repair
through `engine.apply_directive(...)`.

The normative repair mapping is:

| Failure | Ordered advisory repairs |
| --- | --- |
| `PREMISE_ALREADY_SET` | `change premise to <requested value>` |
| `PREMISE_NOT_SET` | `set premise <requested value>` |
| `ITEM_PROHIBITED` | `remove policy <item>`; `use <item>` |
| `ITEM_ALREADY_IN_USE` | `remove policy <item>`; `prohibit <item>` |
| `REPLACEMENT_TARGET_PROHIBITED` | `remove policy <target>`; retry the original replacement directive |
| `REPLACEMENT_SOURCE_PROHIBITED` | no repair (`()`) |
| `REPLACEMENT_SOURCE_MISSING` | no repair (`()`) |

Repairs are canonical, ordered, and advisory only. The engine never applies
them automatically; hosts explicitly select and submit any repair they want to
use. `message` is presentation data, so control flow must use `failure` and
the structured directives rather than parse message text.

Meaning:

| kind | host behavior |
| --- | --- |
| no_directive | no canonical directive recognized; no authoritative state change; host decides what to do next |
| update | canonical directive was accepted; inspect `changed` and use updated state downstream |
| error | canonical directive was rejected semantically; inspect `failure`, show `message`, and optionally offer `repairs` |

`engine.step(...)` is the raw input boundary: it parses user input, may return
`NoDirectiveDecision` when no canonical directive is produced, and performs
semantic evaluation only after canonical parsing succeeds. The canonical
execution boundary is `engine.apply_directive(...)`, which accepts only a
`CanonicalDirective` and returns only `UpdateDecision` or
`SemanticErrorDecision`.

Grammar failures do not produce semantic errors. A semantic error is possible
only after a canonical directive has parsed successfully.

See [docs/api-reference.md](docs/api-reference.md) for the full public API
reference.

Common API entry points:

- engine lifecycle: `Engine()`, `engine.step(...)`,
  `engine.premise`, `engine.policies`, `engine.export_json(...)`,
  `engine.import_json(...)`
- decision variants: `NoDirectiveDecision`, `UpdateDecision`,
  `SemanticErrorDecision`, `SemanticFailure`
- state transport: `engine.export_json(...)`, `engine.import_json(...)`

---

## State Model

The state model holds explicit user commitments that the host can treat as
authoritative in future turns.

- `premise` = authoritative factual or contextual state that changes how future answers should be interpreted
- `use` = affirmative selection or preference
- `prohibit` = explicit exclusion

- Premise is a single value that can be set or replaced
- Policies are per-item (`use` or `prohibit`)
- State changes only through explicit directives
- No inference or semantic reasoning
- Non-canonical input normalization is outside the core state contract

Identical input sequences always produce identical state.

For live engine-owned reads, use `engine.premise` and `engine.policies`.
`engine.policies` returns a caller-owned copy.

Use `engine.export_json()` and `engine.import_json()` for persistence and
restoration.

---

### When to use `premise`

Use `premise` for **persistent background context or factual state that changes how answers should be interpreted**, especially when it:

- applies across many turns
- significantly changes what solutions are valid
- cannot be fully captured as simple `use` / `prohibit` policies

Examples:

- “Current medications: …”
- “Outdoor event; no seating available”
- “GDPR data handling requirements apply”
- “System is deployed across multiple regions”
- “Project deadline is Friday”

In these cases, the premise acts as an **authoritative context anchor** that the host supplies to the model on every turn.

Use policies instead when the constraint is explicit and enforceable:

- “prohibit foods that may cause GI upset”
- “use handheld foods”
- “use concise replies”
- “use a formal tone”
- “prohibit storing personal data beyond immediate use”
- “prohibit introducing new external dependencies”
- “use single-step preparation methods”

### Example domains

Hosts define what policy items and premise mean in context. Common patterns include:

- safety-oriented constraints (for example, prohibited materials or tools)
- authority/evidence constraints (for example, cite only approved sources)
- software workflow constraints (for example, require `uv`, prohibit `npm`)
- accessibility/environment constraints (for example, no audio-only outputs)

Context Compiler enforces explicit directive and state rules. Domain reasoning
still belongs to the host and model workflow.

If a user says something non-canonical such as a near miss, alternate phrasing,
or a failed replacement request that would need reinterpretation, that
normalization is outside core and must happen before canonical directives reach
the compiler.

---

## Persistence Contract

`export_json()` / `import_json()` are the current persistence boundary.

- They transport **authoritative state only**
- Hosts own any broader interaction or session workflow around that state
- Decision objects and advisory repairs are not persisted; persistence carries
  authoritative state only

---

## Directive Examples

Set and change premise for contextual state:

```text
User: set premise project deadline is Friday
User: change premise to project deadline is Thursday
```

Per-item policies:

```text
User: use docker
User: prohibit peanuts
User: use concise replies
User: use a formal tone
```

Replacement:

```text
User: use podman instead of docker
```

If `docker` is absent from saved state, that is a semantic `error`.
Canonical replacement requires an active existing source `use` policy and
does not degrade to plain `use podman`.

Removal and reset:

```text
User: remove policy peanuts
User: reset policies
User: clear state
```

Grammar invariant: a single input never applies more than one canonical
directive.
Directive-shaped invalid input is outside the canonical language, and
`error` is reserved for canonical directives that later fail semantic
evaluation against authoritative state.

A semantic error is a terminal result for the current input. It leaves
authoritative state unchanged and returns the failure classification, failed
canonical directive, ordered advisory repairs, and presentation message.
Repairs are canonical directives. They are advisory only, are never applied
automatically, and require explicit host selection and submission through
`engine.apply_directive(...)`. An absent source item in a canonical replacement
directive is a semantic `error` and does not authorize degradation to plain
`use`.

Examples:

```text
Valid:
use docker
use podman instead of docker
clear state

Invalid:
use docker and prohibit peanuts
clear state then set premise new project

Premise payload (opaque; this is a syntax example, not modeling guidance):
set premise project deadline is Friday and use docker
```

Policy compounds such as `use docker and prohibit peanuts` remain invalid;
premise `VALUE` is opaque and may contain directive-like words.

Quote behavior follows the current grammar literally:

```text
Passthrough (`no_directive`):
"use docker and prohibit peanuts"

Invalid directive:
use "docker and prohibit peanuts"

Canonical directive (`set premise`):
set premise "use docker and prohibit peanuts"
```

Quotes do not create protected literal regions inside a recognized directive
payload.

For the normative grammar, classification rules, and syntax-versus-semantics
boundary, see [DirectiveGrammarSpec.md](docs/DirectiveGrammarSpec.md).

---

## Examples

- [examples](examples/) — minimal usage patterns for the core authority layer
- [demos](demos/) — concrete scenarios showing how behavior differs with and without the compiler
- [`context-compiler-example-integrations`](https://github.com/rlippmann/context-compiler-example-integrations) — runnable application-layer enforcement examples built around compiler state

---

## FAQ

**Isn't this just prompt reinjection?**
No. Prompt construction is one downstream use of authoritative state.
Context Compiler is the authority layer that decides when state changes are
allowed, when a terminal error is required, and which advisory repairs are
available. For runnable application-layer examples, see
[`context-compiler-example-integrations`](https://github.com/rlippmann/context-compiler-example-integrations).

Human-facing interpretation is a separate concern. If you want to recognize
non-canonical phrasing, recover from malformed input, narrow user intent, or
turn a failed replacement request into a different canonical directive, do that
before calling core.

**Why not just use a plain dict?**
A plain dict can hold state for prompt construction, schema selection, tool
gating, and other host behavior.

Context Compiler solves the authority problem: who updates that state, under
which rules, and what happens when instructions conflict.

```text
User: use python_script
User: prohibit python_script
```

Without an authority layer, the application must invent conflict-resolution and
repair rules itself. Context Compiler applies deterministic state-transition
rules and can return a terminal error instead of silently
overwriting state.

---

## Advanced topics

### Guarantees

- State changes only through canonical directives that pass semantic evaluation.
- Identical input sequences produce identical compiler state.
- Model responses never modify compiler state.
- Ambiguous directives trigger error instead of changing state.
- Syntax errors never produce semantic errors or state changes.

Behavioral tests and Hypothesis-based property tests verify these invariants.

### Multiple engines

- [Multiple engines](docs/multi-engine.md)

For a full documentation map, see [docs/README.md](docs/README.md).

---

## Design Notes

These docs cover the design and milestone details:

- [Design philosophy](docs/DesignPhilosophy.md)
- [Architecture boundaries](docs/architecture.md)
- [Project overview](docs/DescriptionAndMilestones.md)
- [Directive grammar specification](docs/DirectiveGrammarSpec.md)

---

### Conformance Fixtures

[`tests/fixtures/`](tests/fixtures/) defines the cross-language conformance tests.
These fixtures serve as the behavioral contract for compiler semantics across implementations.

## Development Process

Most of this project and related projects were implemented with Codex across many development sessions, including substantial implementation, refactoring, and cross-language porting work. ChatGPT was used separately for design discussion, review, and planning. Conformance harnesses and tests were used to verify behavioral consistency rather than treating model output as the correctness check.

---

## License

Apache-2.0.
