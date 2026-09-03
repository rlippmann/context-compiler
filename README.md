# Context Compiler

[![PyPI version](https://img.shields.io/pypi/v/context-compiler)](https://pypi.org/project/context-compiler/)
[![Python versions](https://img.shields.io/pypi/pyversions/context-compiler)](https://pypi.org/project/context-compiler/)
[![License](https://img.shields.io/pypi/l/context-compiler)](https://pypi.org/project/context-compiler/)
[![codecov](https://codecov.io/gh/rlippmann/context-compiler/branch/main/graph/badge.svg)](https://codecov.io/gh/rlippmann/context-compiler)

Context Compiler helps LLM applications keep explicit premise and policy rules
stable across turns. It blocks invalid or conflicting changes and returns
structured decisions.

## Quickstart

Create an engine, send user input to `engine.step(...)`, and use the returned
Decision with the engine’s current state:

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

## CLI and REPL

The package includes an interactive REPL and a machine-readable JSON CLI. See
the [CLI and REPL guide](docs/cli-repl.md) for commands, preload options, and
JSON output behavior.

## Installation

Requirements:

- Python 3.11+

Install:

```bash
pip install context-compiler
```

Packaging notes:

- Base install includes the Context Compiler engine and CLI.
- Example and demo source files are available in the repository and source distribution.
- To run the demos from this repository, clone the repo and install `context-compiler[demos]`.
- The `[demos]` extra installs optional dependencies such as LiteLLM. It does not install demo source files into site-packages.

## API and behavior

The public API is centered on `Engine`, Decision variants, and the
grammar helpers in `context_compiler.grammar`.

- `Engine.step(...)` accepts raw input and may return `no_directive`, `update`,
  or `error`.
- `Engine.apply_directive(...)` accepts a supported directive and returns an
  `update` or `error`.
- `engine.premise` and `engine.policies` expose live compiler state.
- `engine.export_json()` and `engine.import_json(...)` transport compiler state
  only.
See the [API reference](docs/api-reference.md) for fields, signatures, and
repair behavior. See the [Directive Grammar Specification](docs/DirectiveGrammarSpec.md)
for exact syntax and edge cases.

---

## State Model

The engine stores explicit user commitments as saved state:

| State | Meaning |
| --- | --- |
| `premise` | One factual or contextual value that changes how future answers should be interpreted |
| `use` | An affirmative per-item policy |
| `prohibit` | An excluding per-item policy |

State changes only through explicit supported directives. The engine does not
infer meaning or rewrite input.

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

The premise stays in effect until it is changed or cleared.

Use policies instead when the constraint is explicit and enforceable:

- “prohibit foods that may cause GI upset”
- “use handheld foods”
- “use concise replies”
- “use a formal tone”
- “prohibit storing personal data beyond immediate use”
- “prohibit introducing new external dependencies”
- “use single-step preparation methods”

### Example domains

What these rules mean depends on your application. Common patterns include:

- safety-oriented constraints (for example, prohibited materials or tools)
- authority/evidence constraints (for example, cite only approved sources)
- software workflow constraints (for example, require `uv`, prohibit `npm`)
- accessibility/environment constraints (for example, no audio-only outputs)

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

If `docker` is absent from saved state, the replacement fails and leaves state
unchanged. It does not become plain `use podman`.

Removal and reset:

```text
User: remove policy peanuts
User: reset policies
User: clear state
```

Each input can contain at most one supported directive. For example, `use
docker and prohibit peanuts` does not match the supported format.

For exact syntax and edge cases, see
[DirectiveGrammarSpec.md](docs/DirectiveGrammarSpec.md).

---

## Examples

- [examples](examples/) — minimal usage patterns for the Context Compiler engine
- [demos](demos/) — concrete scenarios showing how behavior differs with and without the compiler
- [`context-compiler-example-integrations`](https://github.com/rlippmann/context-compiler-example-integrations) — runnable integrations using compiler state

---

## FAQ

**Isn't this just prompt reinjection?**
No. Prompt construction is one downstream use of saved state.
Context Compiler decides when state changes are allowed, when an error is
required, and which conflicts to report. For runnable application examples, see
[`context-compiler-example-integrations`](https://github.com/rlippmann/context-compiler-example-integrations).

**Why not just use a plain dict?**
A plain dict can hold state for prompt construction, schema selection, tool
gating, and other application behavior.

Context Compiler defines what changes are allowed and reports conflicts instead
of leaving the application to invent those rules.

```text
User: use python_script
User: prohibit python_script
```

Without these rules, conflicting instructions can be handled inconsistently or
silently overwrite state.

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

---

## Advanced topics

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
These fixtures help keep compiler behavior consistent across implementations.

## Development Process (OpenAI Devpost)

Most of this project and related projects were implemented with Codex across many development sessions, including substantial implementation, refactoring, and cross-language porting work. ChatGPT was used separately for design discussion, review, and planning. Conformance harnesses and tests were used to verify behavioral consistency rather than treating model output as the correctness check.

---

## License

Apache-2.0.
