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

## Architectural framing

The preprocessor is a host adaptation layer, not an authoritative state engine.

Model/tool-description translation can help with simple direct cases, but
integrations should not rely on model intent translation alone as the mutation
boundary.

In simpler hosts without an embedded model, this preprocessor provides a
conservative translation path.

In model-assisted hosts, the same conservative boundary still applies: candidate
directives are suggestions until validated.

Both paths feed canonical directives into the same deterministic engine. The
compiler remains authoritative regardless of directive source.

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
Raw model output must never directly mutate state.

Pending clarification rule:

- If the engine has pending clarification state, bypass preprocessing and pass
  raw user input directly to `engine.step(...)`.
- This preserves deterministic continuation behavior because pending resolution
  accepts only confirmation tokens until resolved.

Host handling notes:

- `passthrough` means no directive was applied; the host may call the model with
  unchanged user input.
- `clarify` means mutation is blocked; the host should surface
  `prompt_to_user` and wait for confirmation-style input.
- `update` means a validated canonical directive was applied to authoritative
  state.

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
- Preserve quoted payload tokens in canonical directives; do not silently strip
  payload quotes (for example `use "docker"` remains quoted).
- Prefer false negatives over false positive state mutation.

Natural-language state proposal workflows should be handled by explicit host
assist/proposal flows, not implicit preprocessing.

## Future direction (planning note)

This section is architectural direction, not committed implementation.

Future preprocessing may evolve beyond direct natural-language to directive
canonicalization.

- Policy preprocessing and premise-like facts have different risk profiles.
- Premise-like facts (for example, `I am vegetarian`) may be useful persistent
  context, but are high risk to auto-persist.
- Likely direction:
  - keep directive preprocessing conservative and non-expansive
  - add a separate inspectable, non-mutating suggestion layer for possible
    persistent context
  - require explicit host/user confirmation before any mutation

This aligns with the post-0.7 / 0.8 direction: inspectable, previewable,
non-mutating suggestions with host-mediated confirmation, while the
authoritative engine remains deterministic and explicit.

## Status

This preprocessor surface is experimental and may evolve independently of the
core engine.

For concrete module usage, prompt guidance, and integration details, see:
[`experimental/preprocessor/README.md`](../experimental/preprocessor/README.md).
