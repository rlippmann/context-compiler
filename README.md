# Context Compiler

[![PyPI version](https://img.shields.io/pypi/v/context-compiler)](https://pypi.org/project/context-compiler/)
[![Python versions](https://img.shields.io/pypi/pyversions/context-compiler)](https://pypi.org/project/context-compiler/)
[![License](https://img.shields.io/pypi/l/context-compiler)](https://pypi.org/project/context-compiler/)
[![codecov](https://codecov.io/gh/rlippmann/context-compiler/branch/main/graph/badge.svg)](https://codecov.io/gh/rlippmann/context-compiler)

Context Compiler is a deterministic state authority for LLM applications. It
keeps explicit premise and policy rules stable across turns, blocks invalid or
conflicting state changes, and returns structured results for the host.

The model generates responses; the compiler owns authoritative state. It does
not depend on model compliance, and it never derives state from model output.

## Quickstart

Create an engine, send user input to `engine.step(...)`, and use the returned
Decision plus the engine’s current state in your host workflow:

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

Your app owns the model call. The compiler owns canonical directive execution,
semantic validation, state transitions, and state persistence.

## How it works

Core accepts one canonical directive at a time. It classifies syntax, evaluates
the directive against authoritative state, and returns one of three outcomes:

- `no_directive`: no canonical directive was recognized; the host decides what
  to do next;
- `update`: the directive was accepted and state may have changed; inspect
  `UpdateDecision.changed`; or
- `error`: semantic evaluation blocked the directive; inspect the failure and
  explicitly choose an advisory repair if one is available.

Only canonical directives can mutate state. Non-canonical phrasing,
malformed-input recovery, and intent drafting belong in an acquisition layer
outside core. Runtime behavior that uses saved state belongs to the host’s
application layer.

```text
User input → Context Compiler → Decision → Host application
             owns state          chooses model/runtime behavior
```

For the exact grammar, state-transition rules, and Decision fields, see the
[Directive Grammar Specification](docs/DirectiveGrammarSpec.md) and
[API reference](docs/api-reference.md).

---

## Demos and evidence

The current demo suite in this repository contains 7 scored demos
(`01`-`05`, `07`, `08`) plus 1 informational demo (`06`).

The published verification matrix records 7 model runs from an earlier
8-scored-demo runner across hosted/frontier providers and local Ollama models.
In those published runs,
baseline passed **24 / 56**, reinjected-state passed **40 / 56**, and both
compiler paths passed **56 / 56**.

→ [Current demo set and output modes](demos/README.md)
Current and historical published results: [docs/demos-results.md](docs/demos-results.md)

## Interactive Playground

Use the REPL to explore the grammar and state rules.

```bash
pip install context-compiler
context-compiler
```

The `state` command shows saved state, and `step <input>` is an explicit alias
for normal bare-input behavior. Use `--initial-state-json` or
`--initial-state-file` to preload exported state.

## Machine-Readable CLI Usage

Use `--json` when you want one complete JSON object per processed input line
for non-interactive usage.

```bash
context-compiler --json < input.txt
```

The JSON output uses `output_version: 2`. Updates include `changed`; semantic
errors include `failure`, the failed canonical `directive`, ordered advisory
`repairs`, and `message`. This is a CLI projection of ephemeral Decisions, not
Decision object serialization. Repairs are never applied automatically.

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

## API and behavior

The public API is centered on `Engine`, immutable Decision variants, and the
grammar helpers in `context_compiler.grammar`.

- `Engine.step(...)` accepts raw input and may return `no_directive`, `update`,
  or `error`.
- `Engine.apply_directive(...)` accepts a canonical directive and returns an
  `update` or semantic `error`.
- `engine.premise` and `engine.policies` expose live authoritative state;
  `engine.policies` returns a caller-owned copy.
- `engine.export_json()` and `engine.import_json(...)` transport authoritative
  state only.
- Decisions are immutable. Semantic errors include a failure classification,
  the rejected directive, a presentation message, and ordered advisory repairs;
  repairs are never applied automatically.

See the [API reference](docs/api-reference.md) for fields, signatures, and
repair semantics. See the [Directive Grammar Specification](docs/DirectiveGrammarSpec.md)
for canonical syntax and classification rules.

---

## State Model

The engine stores explicit user commitments as authoritative state:

| State | Meaning |
| --- | --- |
| `premise` | One factual or contextual value that changes how future answers should be interpreted |
| `use` | An affirmative per-item policy |
| `prohibit` | An excluding per-item policy |

State changes only through explicit canonical directives. The engine performs
no inference or semantic reasoning, and non-canonical input normalization is
outside the core state contract.

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

## Development Process (OpenAI Devpost)

Most of this project and related projects were implemented with Codex across many development sessions, including substantial implementation, refactoring, and cross-language porting work. ChatGPT was used separately for design discussion, review, and planning. Conformance harnesses and tests were used to verify behavioral consistency rather than treating model output as the correctness check.

---

## License

Apache-2.0.
