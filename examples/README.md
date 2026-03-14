# Examples

This directory contains small integration examples showing typical host-side usage of the Context Compiler.

## 01_persistent_guardrails.py

Demonstrates how a prohibition persists as authoritative state across later turns.  
Shows the host using compiled state to keep constraints active.

## 02_configuration_and_correction.py

Demonstrates deterministic fact replacement with explicit correction.  
Shows last-write-wins behavior for `facts.focus.primary`.

## 03_ambiguity_with_clarification.py

Demonstrates ambiguity detection before state mutation.  
Shows how the host handles `Decision.kind == "clarify"` and resumes after confirmation.

## 04_tool_governance_denylist.py

Demonstrates tool-governance policy handling via prohibition directives.  
Shows how hosts can prevent denied tools from being selected.

## 05_llm_integration_pattern.py

Demonstrates the end-to-end host control flow around `Decision`.  
Shows when to clarify, when to call the model, and how to include compiled state in prompts.
