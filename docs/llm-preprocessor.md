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

1. heuristic preprocessing
2. validate candidate output
3. LLM fallback preprocessing (only when needed)
4. validate candidate output
5. If a valid directive is produced, pass it to the compiler.
   Otherwise pass the original input unchanged.

All preprocessor outputs, including heuristic outputs, must be validated with
`parse_preprocessor_output(...)` before being applied.

Raw heuristic/LLM outputs must not be passed directly to the compiler.

Pending clarification rule:

- If the engine has pending clarification state, bypass preprocessing and pass
  raw user input directly to `engine.step(...)`.
- This preserves deterministic continuation behavior because pending resolution
  accepts only confirmation tokens until resolved.

## Limits

The preprocessor is best-effort and intentionally conservative. Ambiguous,
reported, quoted, or mixed-intent inputs may still require abstention or host
clarification behavior.

Boundary policy (explicit):

- Whole-message canonicalization only.
- At most one canonical directive may be emitted; otherwise abstain.
- Do not extract directives from surrounding prose, questions, or reporting.
- Do not split sentences or mine multi-line batches for commands.
- Do not extract from markdown/code blocks or quoted/reported text.
- Do not perform broad semantic rewrites.
- Prefer false negatives over false positive state mutation.

Natural-language state proposal workflows should be handled by explicit host
assist/proposal flows, not implicit preprocessing.

## Status

This preprocessor surface is experimental and may evolve independently of the
core engine.

For concrete module usage, prompt guidance, and integration details, see:
[`experimental/preprocessor/README.md`](../experimental/preprocessor/README.md).
