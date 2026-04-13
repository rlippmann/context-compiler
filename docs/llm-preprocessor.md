# LLM Preprocessor (Optional, Experimental)

The experimental preprocessor is an optional host-side layer that can convert
natural-language messages into canonical Context Compiler directives before
compilation.

The compiler remains deterministic and authoritative. The preprocessor does not
replace core parsing or state semantics.

## Required flow

Recommended conceptual flow:

1. heuristic precompile
2. validate candidate output
3. LLM fallback precompile (only when needed)
4. validate candidate output
5. pass validated directive (or original input) to compiler

All preprocessor outputs, including heuristic outputs, must be validated with
`parse_precompiler_output(...)` before being applied.

Raw heuristic/LLM outputs must not be passed directly to the compiler.

## Limits

The preprocessor is best-effort and intentionally conservative. Ambiguous,
reported, quoted, or mixed-intent inputs may still require abstention or host
clarification behavior.

## Status

This preprocessor surface is experimental and may evolve independently of the
core engine.

For concrete module usage, prompt guidance, and integration details, see:
[`experimental/preprocessor/README.md`](../experimental/preprocessor/README.md).
