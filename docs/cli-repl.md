# CLI and REPL

The package includes an interactive REPL for exploring the grammar and state
rules, plus a machine-readable mode for processing input from another tool.

## Interactive REPL

Install the package and start the REPL:

```bash
pip install context-compiler
context-compiler
```

The `state` command shows saved state, and `step <input>` is an explicit alias
for normal bare-input behavior. Use `--initial-state-json` or
`--initial-state-file` to preload exported state.

## Machine-readable CLI

Use `--json` when you want one complete JSON object per processed input line
for non-interactive usage.

```bash
context-compiler --json < input.txt
```

The JSON output uses `output_version: 2`. Updates include `changed`; semantic
errors include `failure`, the failed canonical `directive`, ordered advisory
`repairs`, and `message`. This is a CLI projection of ephemeral Decisions, not
Decision object serialization. Repairs are never applied automatically.
