# LLM Preprocessor (Optional)

An LLM can be used as a preprocessor to convert natural language into canonical Context Compiler directives before compilation.

Example:

```text
maybe avoid docker but actually don't use docker anymore
→ prohibit docker
```

The compiler remains deterministic and authoritative. The preprocessor is optional and external.

## Usage Recommendations

- Default: use heuristic precompilation first, then validator, then LLM fallback.
- This gives the safest behavior: deterministic structural handling plus conservative fallback.
- Use LLM-only mode only when heuristic precompilation is unavailable.
- In LLM-only mode, use stricter prompting and validate outputs before applying them.
- Llama-family models are typically more interpretive in LLM-only mode and may require extra prompt strictness.

## What it does

The preprocessor tries to:

- turn clear instructions into directives
- ignore normal conversation
- return `<NO_DIRECTIVE>` when unsure

It is designed to be conservative:

> if it is not clearly an instruction, it should do nothing.

## Prompt files

Use prompt files from `experimental/preprocessor/prompts/`:

- `default.txt` for most models
- `llama.txt` for Llama-family models

These files are the maintained prompt sources for host-side preprocessor use.

## Prompt rendering helper

Shared prompt rendering lives in `experimental/preprocessor/prompt_utils.py`:

- `render_prompt(path: Path, state) -> str | None`

Behavior:

- reads the prompt file from `path`
- strips leading `#` header comment lines and leading blank lines
- replaces `<NULL_OR_VALUE>` with `null` or current premise
- replaces `<SET OF CURRENT POLICY ITEMS>` with sorted policy keys or `(none)`
- returns `None` if the file cannot be loaded

LLM outputs should be validated before being applied to ensure they match allowed directive forms.

## Examples

```text
use uv and not docker
→ use uv instead of docker

never use docker
→ prohibit docker

you can use docker now
→ remove policy docker

thanks
→ <NO_DIRECTIVE>
```

## What to expect

- Works well for clear instructions
- Handles messy but obvious phrasing
- Stronger models give cleaner results
- Conservative prompting reduces false positives

## Known limits

Some inputs are inherently ambiguous or difficult to interpret. These fall into a few categories.

### Clearly non-directive (should be ignored)

- quoted or reported speech  
  (`he said "use docker"`, `yesterday I said don't use docker`)

These are mentions of directives, not instructions.

### Ambiguous phrasing (may be interpreted either way)

- descriptive statements  
  (`I use docker`)
- questions that imply intent  
  (`can you switch from docker to podman?`)

In normal conversation, these can function as indirect instructions, so models may reasonably interpret them as directives.

### Conflicting instructions

- multiple incompatible signals in one message  
  (`use docker; actually don't use docker`)

These require resolving intent, which is not always clear.

The preprocessor is best-effort. It may occasionally extract a directive where none was intended, especially in ambiguous cases.

The compiler remains the source of truth.

## Model behavior

The preprocessor relies on instruction-following behavior.

In testing:

- stronger models produced cleaner results
- conservative prompting improved precision
- some edge cases remained even on strong models

## Summary

- The preprocessor is helpful, but not required
- It works best on clear instructions
- Some inputs are inherently ambiguous
- The compiler remains in control
