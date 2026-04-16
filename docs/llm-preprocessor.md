# LLM Preprocessor (Optional, Experimental)

The experimental preprocessor is an optional host-side layer that can convert
natural-language messages into canonical Context Compiler directives before
compilation.

The compiler remains deterministic and authoritative. The preprocessor does not
replace core parsing or state semantics.

Install path for integrations using this layer:
`pip install "context-compiler[experimental]"`.

Integration runtimes must use installed-package imports/resources for this
layer. Do not rely on repo-relative preprocessor paths.

## Required flow

Recommended conceptual flow:

1. heuristic precompile
2. validate candidate output
3. LLM fallback precompile (only when needed)
4. validate candidate output
5. If a valid directive is produced, pass it to the compiler.
   Otherwise pass the original input unchanged.

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
