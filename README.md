# Context Compiler

[![PyPI version](https://img.shields.io/pypi/v/context-compiler)](https://pypi.org/project/context-compiler/)
[![Python versions](https://img.shields.io/pypi/pyversions/context-compiler)](https://pypi.org/project/context-compiler/)
[![License](https://img.shields.io/pypi/l/context-compiler)](https://pypi.org/project/context-compiler/)
[![codecov](https://codecov.io/gh/rlippmann/context-compiler/branch/main/graph/badge.svg)](https://codecov.io/gh/rlippmann/context-compiler)

Context Compiler helps LLM applications keep explicit premise and policy rules
stable across turns. It blocks invalid or conflicting changes and returns
structured decisions.

Use it when saved context and policy rules need to shape what an application
does, not just what the model sees or says.

The [`context-compiler-example-integrations`](https://github.com/rlippmann/context-compiler-example-integrations)
show this approach working in applications, and the [demo results](docs/demos-results.md)
show consistent behavior across models and prompt conditions.

## Quickstart

This example shows premise and policy updates directly:

```python
from context_compiler import Engine, SemanticErrorDecision, UpdateDecision

engine = Engine()

engine.step("set premise project deadline is Friday")
print(engine.premise)
# project deadline is Friday

engine.step("change premise to project deadline is Thursday")
print(engine.premise)
# project deadline is Thursday

engine.step("use docker")

result = engine.step("use podman instead of docker")
if isinstance(result, UpdateDecision):
    print(result.changed)
# True

result = engine.step("use podman")
if isinstance(result, UpdateDecision):
    print(result.changed)
# False

result = engine.step("use npm instead of yarn")
if isinstance(result, SemanticErrorDecision):
    print(result.message)

# "yarn" is not currently in use.
# Replacement requires an active 'use' policy.
```

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

The main public API is `Engine` and its Decision results.

- `Engine.step(...)` accepts raw input and may return `no_directive`, `update`,
  or `error`.
- `Engine.apply_directive(...)` accepts a supported directive and returns an
  `update` or `error`.
- `engine.premise` and `engine.policies` expose live compiler state.
- `engine.export_json()` and `engine.import_json(...)` transport compiler state
  only.
See the [API reference](docs/api-reference.md) for fields, signatures, and
repair behavior.

---

## State Model

The engine stores explicit user commitments as saved state:

| State | Meaning |
| --- | --- |
| `premise` | One factual or contextual value that changes how future answers should be interpreted |
| `use` | An affirmative per-item policy |
| `prohibit` | An excluding per-item policy |

### Directive commands

Set or change the premise with:

```text
set premise project deadline is Friday
change premise to project deadline is Thursday
```

Policy commands:

```text
use docker
prohibit peanuts
```

To replace an existing `use` policy:

```text
use podman instead of docker
```

If `docker` is absent from saved state, the replacement fails and leaves state
unchanged. It does not become plain `use podman`.

To remove a policy or clear state:

```text
remove policy peanuts
reset policies
clear state
```

---

### When to use `premise`

Use `premise` for **persistent background context or factual state that changes how answers should be interpreted**, especially when it:

- applies across many turns
- significantly changes what solutions are valid
- cannot be fully captured as simple `use` / `prohibit` policies

Examples:

- `set premise current medications: …`
- `set premise outdoor event; no seating available`
- `set premise GDPR data handling requirements apply`
- `set premise system is deployed across multiple regions`
- `set premise project deadline is Friday`

The premise stays in effect until it is changed or cleared.

Use policies instead when the constraint is explicit and enforceable.

```text
use concise replies
use a formal tone
prohibit introducing new external dependencies
```

## Examples and demos

- [examples](examples/) — minimal usage patterns for the Context Compiler engine
- [demos](demos/) — concrete scenarios showing how behavior differs with and without the compiler
- [`context-compiler-example-integrations`](https://github.com/rlippmann/context-compiler-example-integrations) — runnable integrations using compiler state
- [demo results](docs/demos-results.md) — evidence that the compiler works in practice

---

## CLI and REPL

The package includes an interactive REPL and a machine-readable JSON CLI. See
the [CLI and REPL guide](docs/cli-repl.md) for commands, preload options, and
JSON output behavior.

---

## Documentation

- [Design philosophy](docs/DesignPhilosophy.md)
- [Architecture boundaries](docs/architecture.md)
- [Project overview](docs/DescriptionAndMilestones.md)
- [Directive grammar specification](docs/DirectiveGrammarSpec.md)
- [Multiple engines](docs/multi-engine.md)
- [`tests/fixtures/`](tests/fixtures/) — Cross-language fixtures that help keep compiler behavior consistent across implementations.

For the full map, see [docs/README.md](docs/README.md).

---

## License

Apache-2.0.
