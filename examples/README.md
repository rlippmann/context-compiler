# Examples

This directory contains small authority-layer examples showing typical app-side usage of Context Compiler.

These files are included in the base package install (`pip install context-compiler`).
Non-integration example files in this directory are standalone scripts and can be run directly.

## 01_persistent_guardrails.py

Shows how explicit policy state stays authoritative across later turns.  
Shows the app sending saved state so later answers are interpreted in that context.

## 02_configuration_and_correction.py

Demonstrates premise as authoritative context for future turns.  
Shows `set premise ...` followed by `change premise to ...`.

## 03_ambiguity_with_clarification.py

Shows `clarify` behavior before state changes.  
Shows how the app handles `clarify` and skips the LLM call.

## 08_controller_preview_diff.py

Shows controller-layer dry-run behavior with `preview(engine, user_input)`.  
Shows structural state inspection with `state_diff(state_before, state_after)`.  
Shows `step(engine, user_input)` after preview to apply the same input.

## 05_llm_integration_pattern.py

Shows end-to-end app control flow around compiler outcomes.  
Shows what to do on `clarify`, when to call the model, and how to include saved state in prompts.
Includes a single-item policy removal step via `remove policy <item>`.

## 06_transcript_replay.py

Shows transcript replay helpers for app integration.
Shows `compile_transcript(messages)` from a fresh engine and `engine.apply_transcript(messages)` on current engine state.

## 07_single_policy_correction.py

Demonstrates explicit single-policy correction without `reset policies`.  
Shows `prohibit peanuts` -> `remove policy peanuts` -> `use peanuts`.

## 04_tool_governance_denylist.py

Shows an application-layer use of authoritative policy state for tool selection.  
Shows how apps can prevent denied tools from being selected without changing compiler identity.
