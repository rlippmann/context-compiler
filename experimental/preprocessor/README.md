# Experimental Preprocessor Package

This package provides optional app-layer preprocessing utilities for Context
Compiler integrations.

It is experimental and separate from the deterministic core engine in `src/`.

Model/tool-description translation can help with simple direct cases, but raw
model output is not safe by itself for state changes. The app must validate
outputs before applying them.

In MCP/tool-calling environments, over-eager tool calling on conversational or
ambiguous input is a known failure mode. Conservative preprocessing and
validation help reduce unintended mutation.

Recommended install for integrations using this package:
`pip install "context-compiler[experimental]"`.

Integrations should import this package from the installed environment rather
than using repo-relative preprocessor paths.

Compatibility note:
- Use `heuristic_preprocessor.py` and `parse_preprocessor_output(...)`.

## Modules

- `heuristic_preprocessor.py`: conservative structural preprocessing pass.
- `output_validation.py`: shared normalization and validation checks.
- `prompt_utils.py`: state-aware prompt rendering helper.
- `constants.py`: shared protocol literals and directive validation patterns.
- `prompts/default.txt`: default runtime prompt.
- `prompts/llama.txt`: stricter prompt for Llama-family models in LLM-only mode.

## Validation boundary (required)

Public validator entry point:

- `parse_preprocessor_output(raw_output: object, *, source_input: str | None = None) -> str | None`
- `validate_preprocessor_output(raw_output: object, *, source_input: str | None = None) -> dict`

All preprocessor outputs (heuristic or LLM) must be validated with
`parse_preprocessor_output(...)` before being applied.

Classification contract:

- `directive`: safe, validated canonical directive (`output` is a directive string)
- `no_directive`: confident ordinary content (`output` is `null`)
- `unknown`: unsafe to rewrite (`output` is `null`)

`unknown` is reject/abstain behavior. Malformed, ambiguous, mixed-intent,
quoted/reported, unsupported, or unsafe outputs must not be rewritten.

Only validated `directive` output may be used as rewritten compiler input.
`no_directive` and `unknown` must fall back to original user input.

`source_input` is optional at the API level for backward compatibility.
For integration behavior, it is REQUIRED for LLM fallback validation calls:
pass `source_input=<original user text>` so source-aware reject rules can
block unsafe rewrites.

Engine-owned near-misses are reject cases (for example `set premise to X`,
`change premise X`) and must remain `unknown` (not rewritten).

Raw preprocessor/LLM outputs must not be passed directly to the compiler.
Raw model output must never directly change state.

The preprocessor does not expand directive grammar. It may emit only validated
canonical directives accepted by the compiler.

Conservative boundary policy:

- Only process the full message, not pieces of it (no directive mining from prose).
- Emit at most one canonical directive; otherwise abstain.
- No sentence splitting or hidden multi-line extraction.
- No mixed directive + task extraction.
- No markdown/code-block extraction.
- No broad natural-language semantic rewriting.
- Prefer false negatives over false positives.
- Quoted payload tokens inside an otherwise canonical directive (for example
  `use "docker"`) are preserved as-is; they are not silently unquoted.

If you need natural-language proposal behavior, use an explicit host workflow
that shows suggestions first and asks for confirmation.

## Safe usage pattern

1. Run `preprocess_heuristic(message)`.
2. If a heuristic candidate directive exists, validate it with
   `parse_preprocessor_output(...)`.
3. If no valid directive was produced, run LLM fallback preprocess.
4. Validate fallback output with
   `parse_preprocessor_output(..., source_input=message)`.
5. If a valid directive is produced, pass it through a normal compiler input path.
   For session-owned integrations, use `engine.step(...)`.
   For transcript-based integrations that receive full chat history each turn:
   - use `context_compiler.compile_transcript(...)` for stateless evaluation
   - use `engine.apply_transcript(...)` to update an existing engine
   Otherwise pass the original user input unchanged.

Decision handling reminder:
- `passthrough`: no directive was applied; handle as ordinary user input.
- `clarify`: mutation is blocked; surface `prompt_to_user` and do not treat
  state as updated.
- `update`: validated canonical directive applied; use updated state as
  the source of truth.

## Future direction (planning note)

This section is architectural direction, not committed implementation.

Future preprocessing may evolve beyond direct natural-language to directive
conversion.

- Policy directives and premise-like facts have different risk profiles.
- Premise-like facts (for example, `I am vegetarian`) may be useful persistent
  context, but should not be auto-persisted without confirmation.
- Likely direction:
  - conservative directive preprocessing remains separate
  - a possible suggestion layer is inspectable, non-mutating, and previewable
  - user confirms before anything is saved

## Prompt guidance

- Use `prompts/default.txt` as the recommended default prompt.
- Use `prompts/llama.txt` only for LLM-only preprocessing with Llama-family
  models.
- Heuristic-first integrations should still keep `default.txt` as the normal
  fallback prompt unless there is a model-specific reason not to.

## Prompt rendering helper

`prompt_utils.py` exposes:

- `render_prompt(path: Path, state: State) -> str | None`

Behavior:

- reads prompt text from `path`
- strips leading `#` header lines and leading blank lines
- replaces `<NULL_OR_VALUE>` and `<SET OF CURRENT POLICY ITEMS>` using state
- returns `None` if prompt loading fails

## Notes

- This package does not mutate compiler state directly.
- State changes still occur only through compiler parsing/replay paths.
