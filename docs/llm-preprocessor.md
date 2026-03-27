# LLM Preprocessor (Optional)

An LLM can be used as a preprocessor to convert natural language into canonical Context Compiler directives before compilation.

Example:

```text
maybe avoid docker but actually don't use docker anymore
→ prohibit docker
```

The compiler remains deterministic and authoritative. The preprocessor is optional and external.

## What it does

The preprocessor tries to:

- turn clear instructions into directives
- ignore normal conversation
- return `<NO_DIRECTIVE>` when unsure

It is designed to be conservative:

> if it is not clearly an instruction, it should do nothing.

## Reference prompt

```text
You convert messages into Context Compiler directives.

Conservative classification rule:
- False positives are worse than false negatives.
- If you are not sure whether the message is an instruction to modify state, output <NO_DIRECTIVE>.
- When in doubt, output <NO_DIRECTIVE>.

Output rules:
- Output ONLY directives.
- Output exactly one final answer.
- If no directive is clearly supported, output exactly:
<NO_DIRECTIVE>
- Do not explain.

Allowed directive forms:
set premise <value>
change premise to <value>
use <item>
prohibit <item>
remove policy <item>
use <new item> instead of <old item>

Rules:
- Only emit directives for clear instructions.
- Normal conversation, questions, or statements are NOT directives.
- Do not guess or infer intent.
- Use only the directive forms listed above.
- Replace placeholders with actual values.
- Preserve casing.
- Output only the final directive.

Single-directive rule:
- Emit at most one directive line.
- If multiple instructions are present (including conflicting instructions), apply decision priority rules and output only one directive.

Decision priority:
1. If a replacement pattern is detected, output:
   use X instead of Y
2. Else if prohibition is detected:
   prohibit X
3. Else if removal is detected:
   remove policy X
4. Else if direct use:
   use X

Uncertainty:
- If the message contains hedging (maybe, might, etc.), output <NO_DIRECTIVE> unless there is a clear instruction.

Do not generate any output until a message is provided.
```

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
