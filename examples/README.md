# Examples

This directory contains small integration examples showing typical host-side usage of the Context Compiler.

These files are included in the base package install (`pip install context-compiler`).

## 01_persistent_guardrails.py

Demonstrates how a prohibition persists as authoritative state across later turns.  
Shows the host using compiled state to keep constraints active.

## 02_configuration_and_correction.py

Demonstrates explicit premise lifecycle in 0.5.  
Shows `set premise ...` followed by `change premise to ...`.

## 03_ambiguity_with_clarification.py

Demonstrates contradiction clarify behavior before state mutation.  
Shows how the host handles clarify results and blocks LLM calls.

## 04_tool_governance_denylist.py

Demonstrates tool-governance policy handling via prohibition directives.  
Shows how hosts can prevent denied tools from being selected.

## 05_llm_integration_pattern.py

Demonstrates end-to-end host control flow around compiler outcomes.  
Shows when to clarify, when to call the model, and how to include compiled state in prompts.
Includes a single-item policy removal step via `remove policy <item>`.

## 06_transcript_replay.py

Demonstrates transcript replay helpers for host integration.
Shows `compile_transcript(messages)` from a fresh engine and `engine.apply_transcript(messages)` on current engine state.

## 07_single_policy_correction.py

Demonstrates explicit single-policy correction without `reset policies`.  
Shows `prohibit peanuts` -> `remove policy peanuts` -> `use peanuts`.
