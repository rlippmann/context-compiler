# Examples

This directory contains small authority-layer examples showing core engine usage
patterns in Context Compiler.

These examples are intended to teach:

- directive grammar
- `Decision` handling
- engine lifecycle
- state access
- checkpoints
- controller APIs
- authority-layer usage patterns

Install the core package with:

```bash
pip install context-compiler
```

Example files in this directory are included in the repository and source distribution, and can be run directly.

They are not intended to be the primary source of framework, provider, or
production runtime integration guidance.

For runnable application-layer enforcement-point and host integration examples,
see
[`context-compiler-example-integrations`](https://github.com/rlippmann/context-compiler-example-integrations).

## 01_persistent_guardrails.py

Shows how explicit policy state stays authoritative across later turns.  
Shows core authority-layer state being used in later turns.

## 02_configuration_and_correction.py

Demonstrates premise as authoritative context for future turns.  
Shows `set premise ...` followed by `change premise to ...`.

## 03_ambiguity_with_clarification.py

Shows `clarify` behavior before state changes.  
Shows how the app handles `clarify` and skips the LLM call.

## 04_tool_governance_denylist.py

Shows an application-layer use of authoritative policy state for tool selection.  
Shows how apps can prevent denied tools from being selected without changing compiler identity.

## 05_llm_integration_pattern.py

Shows end-to-end app control flow around compiler outcomes.  
Shows what to do on `clarify`, when to call the model, and how host code can
use saved state downstream.
Includes a single-item policy removal step via `remove policy <item>`.

## 06_step_sequence_and_checkpoint.py

Shows the recommended authority-layer sequencing pattern with `engine.step(...)`.
Shows checkpoint export/import for restoring authoritative state without replay helpers.

## 07_single_policy_correction.py

Demonstrates explicit single-policy correction without `reset policies`.  
Shows `prohibit peanuts` -> `remove policy peanuts` -> `use peanuts`.

## 08_controller_preview_diff.py

Shows controller-layer dry-run behavior with `preview(engine, user_input)`.  
Shows structural state inspection with `state_diff(state_before, state_after)`.  
Shows `step(engine, user_input)` after preview to apply the same input.
