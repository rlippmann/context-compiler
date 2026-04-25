# Experimental Preprocessor Package

This package provides optional host-layer preprocessing utilities for Context
Compiler integrations.

It is experimental and separate from the deterministic core engine in `src/`.

Recommended install for integrations using this package:
`pip install "context-compiler[experimental]"`.

Integrations should import this package from the installed environment rather
than using repo-relative preprocessor paths.

## Modules

- `heuristic_precompiler.py`: conservative structural precompile pass.
- `output_validation.py`: shared normalization/validation boundary.
- `prompt_utils.py`: state-aware prompt rendering helper.
- `constants.py`: shared protocol literals and directive validation patterns.
- `prompts/default.txt`: default runtime prompt.
- `prompts/llama.txt`: stricter prompt for Llama-family models in LLM-only mode.

## Validation boundary (required)

Public validator entry point:

- `parse_precompiler_output(raw_output: object, *, source_input: str | None = None) -> str | None`
- `validate_precompiler_output(raw_output: object, *, source_input: str | None = None) -> dict`

All preprocessor outputs (heuristic or LLM) must be validated with
`parse_precompiler_output(...)` before being applied.

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

The precompiler does not expand directive grammar. It may emit only validated
canonical directives accepted by the compiler.

## Safe usage pattern

1. Run `precompile_heuristic(message)`.
2. If a heuristic candidate directive exists, validate it with
   `parse_precompiler_output(...)`.
3. If no valid directive was produced, run LLM fallback precompile.
4. Validate fallback output with
   `parse_precompiler_output(..., source_input=message)`.
5. If a valid directive is produced, pass it through a normal compiler input path.
   For session-owned integrations, use `engine.step(...)`.
   For transcript-based integrations that receive full chat history each turn:
   - use `context_compiler.compile_transcript(...)` for stateless evaluation
   - use `engine.apply_transcript(...)` to update an existing engine
   Otherwise pass the original user input unchanged.

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
