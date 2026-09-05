# Context Compiler

Reliable state handling for LLM conversations

## Project Purpose

LLM systems are strong at reasoning, but they can lose consistency across turns.
Corrections may compete with earlier instructions, topics can leak between
conversations, and state can conflict over time.
This project adds a deterministic state layer that is independent of the model.
The model handles interpretation and generation; the engine handles premise and
policies. Only explicit user directives can change state.
When the model reasons and the engine owns state, behavior stays reliable
without retraining the model. The system never derives authoritative state from
model responses.
The goal is not to make the model smarter, but to make interactions
predictable: once a statement is corrected or scoped, future responses
must respect that change.

The engine is a deterministic state machine. It is not a memory or
reasoning layer.

## Architectural Principle

The state engine is the source of truth and is model-independent.
Model output is never interpreted to derive or modify state.
All state transitions originate from explicit user directives.

Context Compiler remains deterministic conversational state authority.

Behavioral details are defined in `docs/DirectiveGrammarSpec.md`.

## Project Milestones

### M1 — Deterministic State Engine (implemented)

**Goal**
Explicit user commitments persist reliably within a conversation.
A change directive replaces previously set state. It does not judge whether earlier conversation content was "correct."

M1 established deterministic state transitions and explicit error behavior.
The current authoritative state shape and directive semantics are defined in `DirectiveGrammarSpec.md` (0.5 / schema version 2).

**Core capability:**

- Recognize explicit user directives that mutate premise or policies
- Apply explicit state changes as deterministic replacements
- Block ambiguous updates until clarified
- Maintain a source-of-truth state that does not depend on prior model wording
- Provide structured state for app-provided model context

**Deliverables:**

- Directive grammar (conservative pattern set)
- State data model (authoritative conversational state)
- Deterministic update rules for explicit directives and error
- Clarification mechanism for ambiguous mutations
- Context serialization interface (`export_json` / `import_json`, state → app layer)
- Reference integration harness (example host)
- Tests: persistence and non-regression of deterministic state updates

**User-visible outcome:**

After correcting or constraining the assistant once, the behavior remains consistent for the rest of the conversation.

### M3 — Cross-Session Recall (implemented, engine-level / host-enabled)

**Goal**
Help apps safely reuse saved exported state.

**Core capability:**

- Export current authoritative state
- Initialize a new engine from previously exported authoritative state
- Ensure restored authoritative state behaves identically to live state

**Deliverables:**

- App-side storage and recovery patterns built on the existing import/export API

**User-visible outcome:**

When apps persist exported state, assistants can carry decisions across
sessions without reintroducing old conflicts.

`export_json()` / `import_json()` are the authoritative persistence boundary.
Long-term memory remains an app persistence responsibility, not an engine-owned
store.

### 0.6.x

The 0.6.x line expanded authority-layer boundary hardening and
regression/conformance surfaces that prepared the project for the later clean
break between core authority behavior, acquisition-layer drafting, and
runnable integrations.

### 0.7 — Auditability & Boundary Hardening

**Goal**
Make engine behavior inspectable and externally controllable without guessing.

**Core capability:**

- State inspection
- Deterministic dry-run / preview
- Structural state diff
- Thin stateless controller layer around step / preview behavior
- Machine-readable REPL JSON output containing:
  - versioned one-object-per-line output (`output_version`)
  - step / preview / state command result envelopes
  - structured Decision fields for update changes and semantic errors
- JSON preload for authoritative state:
  - `--initial-state-json`
  - `--initial-state-file`

**Constraints:**

- No expansion of authoritative state model
- No implicit behavior
- No heuristic-heavy parsing
- Preserve separation between engine/controller authority behavior and
  host-owned acquisition or application layers

### 0.8 — Architectural Decomposition (approved direction)

0.8 documented the clean-break repository split and removed ambiguity about
which package owns which behavior.

Historical 0.8 ownership (superseded for the 0.9 line):

- `context-compiler` owns the Authority Layer:
  deterministic state transitions, canonical directive application, semantic
  validation, error and confirmation handling, preview/diff,
  controller behavior, and authoritative state
- `context-compiler-directive-drafter` owns Acquisition Layer drafting:
  natural-language-to-directive drafting, candidate directive generation,
  malformed-input recovery, alternate human phrasing, prompt/resource usage for
  drafting, and drafting-oriented surfaces
- `context-compiler-example-integrations` owns runnable integrations:
  LiteLLM, OpenWebUI, Ollama, and other proxy/runtime/provider examples

Boundary:

- drafting is non-authoritative
- only core applies directives
- only core mutates authoritative state
- core is the canonical directive and execution layer, not the general
  human-input repair layer

Historical note:

> The experimental preprocessor work was extracted from core into:
>
> `context-compiler-directive-drafter`

Retired in 0.9:

- public preview / dry-run API
- public structural diff API
- public controller result-envelope helpers
- REPL `preview` command
- public surface area that primarily supported the earlier checkpoint,
  continuation, and confirmation-oriented architecture

### Future Consideration — Engine Thread Safety

Current contract:

- Engine instances are deterministic.
- Engine instances are not currently advertised as thread-safe.
- Hosts should serialize access to a shared engine instance.

Design notes:

- Simple locking around `step()` is likely insufficient.
- Any future thread-safety work should evaluate:
  - export/import consistency
  - concurrency testing
- Thread-safety should be designed holistically rather than added through ad hoc locking.

Status:

- Future infrastructure hardening.
- No current release target.

### 0.9 — Authority Surface Cleanup and Conformance Hardening

0.9 completed the clean-break authority-layer release. It:

- retired the public controller, preview, structural-diff, and continuation/
  confirmation-era surfaces;
- established direct `Engine.step(...)` and `Engine.apply_directive(...)`
  execution boundaries;
- established engine-owned premise and policy inspection through
  `engine.premise` and `engine.policies`;
- consolidated the immutable `Decision` variants, semantic error results, and
  advisory canonical repairs;
- established the shared public grammar module and its canonical directive
  surface; and
- hardened package-root, grammar, state-transport, and cross-language
  conformance contracts.

The authority, acquisition, and application boundaries are explicit: core
parses and executes canonical directives and owns authoritative state, while
drafting and runtime integration remain outside the core authority layer.

### 0.10 Candidate Direction — Authority Extensions and Export Integrity

Candidate work for 0.10 includes:

- restricted policy operands;
- read-only premise and policy behavior;
- case-sensitive matching;
- possible partial policy matching as exploratory work; and
- canonical export integrity and hashing.

### Post-0.9 Direction

- 0.10 candidate direction: canonical export integrity and hashing
- MCP adapter likely as a separate/later track after post-clean-break package
  boundaries are fully settled
- Optional MCP-readiness helpers only if narrowly justified
- Additional tooling built on current engine inspection and persistence APIs

### 1.0 Target

Conceptual completion is a stable minimal contract, not feature accumulation.

- Stable minimal engine contract
- Deterministic and inspectable behavior
- Strict authority / acquisition / application separation
- No implicit behavior
- No authoritative state-model expansion
- Cross-language consistency with Python as source of truth
