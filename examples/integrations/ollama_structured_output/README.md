# Ollama structured output (host-side selection)

This example shows a visible host behavior change that is different from prompt reinjection.

Flow:

`Context Compiler state -> host schema decision -> Ollama format request -> model call`

The host reads compiled policy state, picks a JSON Schema (or none), and sends that choice through Ollama's `format` field.

## What this example guarantees

- Context Compiler provides deterministic state transitions.
- The host integration decides whether to request a schema.
- Ollama structured output is a runtime request made by the host.
- If policy state is unknown or insufficient, the host requests no schema.

## What `prohibit shell_command` means here

- The host will not request the `shell_command` schema.
- The host may still request a different schema when policy supports it (for example, `python_script`).
- This does not block normal language discussion about shell commands.

## Observable behavior

Given policy state:

```text
use python_script
prohibit shell_command
```

this host selects `python_script` schema and does not request `shell_command` schema.

## Test boundary

Tests verify schema selection behavior only:

- compiler state -> selected schema (or no schema)
- contradiction handling stays in compiler `clarify`

Tests do not assert exact model wording.

## Run without Ollama

```shell
uv run python examples/integrations/ollama_structured_output/example.py
```

## Optional Ollama smoke run

```shell
export RUN_OLLAMA_SMOKE=1
export OLLAMA_MODEL=llama3.1
uv run python examples/integrations/ollama_structured_output/example.py
```

When smoke mode is enabled, the host sends the selected JSON Schema through Ollama `format`.
