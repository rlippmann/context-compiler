# LLM Preprocessor (Optional, Experimental)

The experimental preprocessor is an optional app-side layer that can convert
natural-language messages into canonical Context Compiler directives before
compilation.

The compiler keeps state rules fixed. The preprocessor does not replace core
parsing or state rules.

Install path for integrations using this layer:
`pip install "context-compiler[experimental]"`.

Integration runtimes must use installed-package imports/resources for this
layer. Do not rely on repo-relative preprocessor paths.

## Architectural framing

The preprocessor is a helper layer in your app, not the source of truth for
state changes.

Model/tool-description translation can help with simple direct cases, but
integrations should not rely on model intent translation alone to decide when
state changes.

In simpler hosts without an embedded model, this preprocessor provides a
conservative translation path.

In model-assisted hosts, the app still checks outputs before applying them.

Both paths send canonical directives to the same deterministic engine. The
engine still controls state updates.

In MCP/tool-calling environments, over-eager tool calling on conversational or
ambiguous input is a known failure mode. Conservative preprocessing and
validation help reduce unintended mutation.

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
Raw model output must never directly change state.

Pending clarification rule:

- If the engine has pending clarification state, bypass preprocessing and pass
  raw user input directly to `engine.step(...)`.
- This keeps confirmation flows correct: while confirmation is pending, only
  confirmation-style input should resolve it.

Host handling notes:

- `passthrough`: no directive was applied; handle as ordinary user input.
- `clarify`: mutation is blocked; surface `prompt_to_user` and do not treat
  state as updated.
- `update`: the app applied a validated directive; use updated state as the
  source of truth.

## Limits

The preprocessor is best-effort and intentionally conservative. Ambiguous,
reported, quoted, or mixed-intent inputs may still require abstention or host
clarification behavior.

Boundary policy (explicit):

- Only process the full message, not pieces of it.
- At most one canonical directive may be emitted; otherwise abstain.
- Do not extract directives from surrounding prose, questions, or reporting.
- Do not split sentences or mine multi-line batches for commands.
- Do not extract from markdown/code blocks or quoted/reported text.
- Do not perform broad semantic rewrites.
- Preserve quoted payload tokens in canonical directives; do not silently strip
  payload quotes (for example `use "docker"` remains quoted).
- Prefer false negatives over false positive state mutation.

If you want natural-language proposals for state, handle that in an explicit
host flow. Do not treat implicit preprocessing as state mutation.

## Future direction (planning note)

This section is architectural direction, not committed implementation.

Future preprocessing may evolve beyond direct natural-language to directive
conversion.

- Policy preprocessing and premise-like facts have different risk profiles.
- Premise-like facts (for example, `I am vegetarian`) may be useful persistent
  context, but should not be auto-persisted without confirmation.
- Likely direction:
  - keep conservative directive preprocessing separate
  - add a possible suggestion layer that is inspectable, non-mutating, and
    previewable
  - require explicit host/user confirmation before any mutation

This aligns with the post-0.7 / 0.8 direction: inspectable, previewable,
non-mutating suggestions that users review first and confirm before saving,
while the engine keeps state rules explicit and repeatable.

## Status

This preprocessor surface is experimental and may evolve independently of the
core engine.

For concrete module usage, prompt guidance, and integration details, see:
[`experimental/preprocessor/README.md`](../experimental/preprocessor/README.md).
