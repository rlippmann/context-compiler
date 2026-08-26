# Context Compiler - Core Directive Grammar Specification (Normative)

## Goal

Define the canonical core directive language for Context Compiler.

This specification is the normative contract for:

- directive classification;
- canonical directive syntax;
- permitted normalization before classification and parsing;
- the boundary between syntax and semantics.

Core is intentionally narrow. It does not:

- repair malformed directives;
- infer missing operands;
- reinterpret near-canonical syntax;
- convert malformed input into another directive;
- parse multiple directives from one input;
- perform natural-language understanding.

Later implementation and conformance work must follow this document.

## 1. Terminology

| Term | Meaning |
| --- | --- |
| User input | Raw text submitted to core |
| Canonical directive | An input that matches one grammar production in Section 7 |
| Directive-shaped input | Input that begins with a canonical directive introducer but fails canonical grammar |
| Passthrough | Input that is not a canonical directive and not directive-shaped invalid input |
| Premise | Single sticky explicit slot controlled only by premise directives |
| Policy | Per-item authoritative state: `"use"` or `"prohibit"` |
| State | Current authoritative snapshot |
| Semantic evaluation | State-dependent evaluation that occurs only after a canonical directive parses successfully |
| Decision | Compiler instruction returned to the host |

`error` is a semantic outcome, not a parsing category.

## 2. System Responsibilities

The compiler:

1. Classifies raw input using the rules in Sections 5 and 6.
2. Parses canonical directives using the grammar in Section 7.
3. Performs semantic evaluation only after successful canonical parsing.
4. Applies deterministic state transitions only for semantically valid canonical directives.
5. Returns a deterministic `Decision`.

The compiler never calls an LLM.
Raw input enters through `step(raw_input)`. Canonical directives may also enter
through `apply_directive(directive)` after the host has parsed or otherwise
validated them at the grammar boundary. All authoritative mutations originate
from canonical directives evaluated through one of these engine boundaries.

## 3. Host Responsibilities

The host:

- handles `no_directive` input outside core;
- displays error prompts when core returns `error`;
- calls the LLM only when the returned `Decision.kind` allows it;
- may perform non-canonical drafting or repair before calling core.

## 4. Decision API Contract

```python
class DecisionKind(StrEnum):
    NO_DIRECTIVE = "no_directive"
    UPDATE = "update"
    ERROR = "error"

Decision = NoDirectiveDecision | UpdateDecision | SemanticErrorDecision

@dataclass(frozen=True, slots=True)
class NoDirectiveDecision:
    kind = DecisionKind.NO_DIRECTIVE

@dataclass(frozen=True, slots=True)
class UpdateDecision:
    kind = DecisionKind.UPDATE
    changed: bool

@dataclass(frozen=True, slots=True)
class SemanticErrorDecision:
    kind = DecisionKind.ERROR
    failure: SemanticFailure
    directive: CanonicalDirective
    repairs: tuple[CanonicalDirective, ...]
    message: str  # derived property
```

Decision values are immutable and ephemeral. They are not persisted and do not
provide mapping or serialization behavior.

`UpdateDecision.changed` reports whether authoritative state actually changed.
An accepted idempotent directive remains an `update` with `changed=False`.

`SemanticErrorDecision.failure` is the machine-readable semantic failure
classification. Its `directive` is the canonical directive rejected by
semantic evaluation. Its `message` is derived human-readable text, and its
`repairs` is an ordered tuple of advisory canonical directives. Repairs are
never applied automatically; hosts explicitly choose whether to submit one
through `apply_directive(...)`. An empty tuple means no deterministic repair
was proposed.

The repair mapping is normative. When a listed repair is returned, repairs
appear in the following order and use the operands from the failed canonical
directive:

| Failure | Ordered advisory repairs |
| --- | --- |
| `PREMISE_ALREADY_SET` | `change premise to <requested value>` |
| `PREMISE_NOT_SET` | `set premise <requested value>` |
| `ITEM_PROHIBITED` | `remove policy <item>`; `use <item>` |
| `ITEM_ALREADY_IN_USE` | `remove policy <item>`; `prohibit <item>` |
| `REPLACEMENT_TARGET_PROHIBITED` | `remove policy <target>`; retry the original replacement directive |
| `REPLACEMENT_SOURCE_PROHIBITED` | no repair (`()`) |
| `REPLACEMENT_SOURCE_MISSING` | no repair (`()`) |

Every repair is a `CanonicalDirective`. Repairs are ordered and advisory only:
the engine never applies them automatically, and a host must explicitly select
and submit any repair through `apply_directive(...)`. A host may decline all
repairs. The `message` field is presentation data; hosts must use `failure` and
the structured directives for control flow rather than parse the message.

Semantics:

- `no_directive`: no canonical directive was recognized by core, no authoritative
  state change was made, and the host decides what to do next
- `update`: canonical directive parsed and semantic evaluation completed without
  a blocking conflict; `changed` reports whether state actually changed
- `error`: canonical directive parsed, but semantic evaluation could not safely
  execute under current authoritative state

`step(raw_input)` is the raw input boundary. It parses the input, may return
`NoDirectiveDecision` when no canonical directive is produced, and performs
semantic evaluation only after canonical parsing succeeds. It returns any of
the three variants. `apply_directive(directive)` is the canonical execution
boundary: it accepts only `CanonicalDirective` and returns only
`UpdateDecision` or `SemanticErrorDecision`; it never returns
`NoDirectiveDecision` and does not parse raw input.

Grammar failures are not semantic errors. A semantic error can occur only
after successful canonical parsing. The failed `CanonicalDirective` is always
available on the error result.

This specification does not add a new runtime `Decision.kind` for
directive-shaped invalid input. Section 6 defines that classification
normatively for future parser and conformance work.

## 5. Engine/Host State Contract

State is a deterministic snapshot:

```json
{
  "premise": null,
  "policies": {},
  "version": 2
}
```

Where:

- `premise`: `string | null`
- `policies`: `dict[string, "use" | "prohibit"]`
- `version`: integer schema version

Properties:

- premise is explicit and sticky;
- policies are authoritative per item;
- policy key absence means no policy for that item;
- no policy ordering, recency, or history semantics exist in core.

## 6. Permitted Normalization and Classification

### 6.1 Lexical normalization before classification

Before classifying raw input as no_directive, directive-shaped invalid input, or
canonical directive, core must apply lexical normalization only for
presentation-level differences.

The normalization pipeline is:

```text
raw input
    ↓
lexical normalization
    ↓
canonical parsing
    ↓
semantic evaluation
```

Permitted lexical normalization is limited to:

1. trimming leading and trailing ASCII whitespace;
2. treating horizontal ASCII whitespace (`SP` and `TAB`) as equivalent token
   separators;
3. collapsing one or more consecutive horizontal ASCII whitespace characters
   between tokens into a single canonical separator;
4. matching directive keywords case-insensitively.

Directive keyword matching is ASCII-only. Unicode normalization is not applied
to directive keywords: NFC, NFD, NFKC, and NFKD compatibility or composition
forms must not turn non-ASCII characters into valid directive keywords. ASCII
case-insensitivity maps only `A`-`Z` to `a`-`z`.

Additional limits:

1. Keyword case-insensitivity applies only to directive keywords and fixed
   grammatical separators defined in Section 7.
2. Parsed operand text must be preserved exactly other than boundary whitespace made
   insignificant by item 1 above.
3. Quote characters still have no grouping or escaping semantics.
4. Terminal punctuation still has no stripping behavior.
5. No token insertion, deletion, replacement, or reordering is permitted.

In particular, lexical normalization must not:

- insert or remove keywords;
- reorder tokens;
- repair incomplete `instead of` forms;
- interpret unexpected tokens;
- lowercase or otherwise rewrite operand text;
- strip punctuation from operands;
- interpret aliases such as `allow`, `replace`, `switch`, or `rather than`.

### 6.2 Classification categories

Every raw input must be classified into exactly one of these categories before
semantic evaluation:

1. `no_directive`
2. directive-shaped invalid input
3. canonical directive

### 6.3 No directive

Input is `no_directive` when it does not begin with a canonical directive
introducer recognized under Section 6.1 and cannot be classified as a
directive-shaped attempt under Section 6.4.

Examples:

- `hello there`
- `"use docker"`
- `allow docker`

### 6.4 Directive-shaped invalid input

Input is directive-shaped invalid input when it begins with one of the
canonical directive introducers below, but the full input fails the canonical
grammar in Section 7:

- `set premise`
- `change premise to`
- `use`
- `prohibit`
- `remove policy`
- `clear premise`
- `reset policies`
- `clear state`

This category includes:

- empty or incomplete directive forms;
- near-canonical forms with extra or missing required tokens;
- compound inputs that attempt more than one directive;
- malformed replacement attempts beginning with `use`.

Examples:

- `set premise`
- `set premise to concise`
- `change premise to`
- `use`
- `use instead of docker`
- `use podman instead of`
- `use docker and prohibit peanuts`
- `clear state then set premise project`

Directive-shaped invalid input is a grammar failure. It is not semantic
`error`.

### 6.5 Canonical directive

Input is a canonical directive only when it matches exactly one grammar
production in Section 7 after applying no more than the lexical normalization
permitted in Section 6.1.

## 7. Canonical Directive Grammar

Only the productions in this section are canonical directives.

Notation:

- directive keywords are matched after Section 6.1 lexical normalization;
- concatenation is literal and order-sensitive;
- `VALUE` and `ITEM` are non-empty raw substrings subject to the restrictions
  below;
- `SP` means one canonical horizontal-whitespace separator after Section 6.1
  normalization.

```text
SET_PREMISE    := "set premise" SP VALUE
CHANGE_PREMISE := "change premise to" SP VALUE
USE_ITEM       := "use" SP ITEM
PROHIBIT_ITEM  := "prohibit" SP ITEM
REMOVE_POLICY  := "remove policy" SP ITEM
REPLACE_USE    := "use" SP REPLACE_NEW " instead of " REPLACE_OLD
CLEAR_PREMISE  := "clear premise"
RESET_POLICIES := "reset policies"
CLEAR_STATE    := "clear state"
```

### 7.1 `VALUE`

`VALUE` is a non-empty raw substring after the required prefix.

Rules:

- must contain at least one non-whitespace character;
- may contain spaces and punctuation;
- is opaque payload: directive keywords, conjunctions, and multiple sentences
  inside `VALUE` are not inspected as embedded directives;
- has no quote-aware or escape-aware subgrammar;
- a separate canonical directive beginning on a new line is still rejected as
  a compound attempt under Section 7.5.

Canonical meaning:

- `SET_PREMISE`: set premise value to `VALUE`
- `CHANGE_PREMISE`: replace premise value with `VALUE`

Malformed examples:

- `set premise`
- `change premise to`
- <code>set premise  </code>

Near-canonical invalid example:

- `set premise to concise`

### 7.2 `ITEM`

`ITEM` is a non-empty raw substring after the required prefix.

Rules:

- must contain at least one non-whitespace character;
- may contain spaces and punctuation;
- has no quote-aware or escape-aware subgrammar;
- for `USE_ITEM`, must not contain the exact delimiter ` instead of `;
- is rejected if the full input would otherwise constitute a compound attempt
  under Section 7.5.

Canonical meaning:

- `USE_ITEM`: assert policy `<ITEM> -> use`
- `PROHIBIT_ITEM`: assert policy `<ITEM> -> prohibit`
- `REMOVE_POLICY`: remove policy for `<ITEM>`

Malformed examples:

- `use`
- `prohibit`
- `remove policy`

### 7.3 Replacement

`REPLACE_USE` is an established canonical directive family in the current
repository contract.

Repository evidence:

- named grammar family in the public grammar module
  ([src/context_compiler/grammar.py](../src/context_compiler/grammar.py));
- documented canonical directive in README and API docs
  ([../README.md](../README.md), [api-reference.md](api-reference.md));
- covered as a first-class directive family in tests
  ([../tests/test_grammar.py](../tests/test_grammar.py),
  [../tests/test_engine.py](../tests/test_engine.py)).

Canonical production:

```text
REPLACE_USE := "use" SP REPLACE_NEW " instead of " REPLACE_OLD
```

Rules:

- both `REPLACE_NEW` and `REPLACE_OLD` must be non-empty;
- the delimiter is the exact literal string ` instead of `;
- no alternate delimiter or verb is canonical;
- no missing-side form is canonical;
- source and target order is fixed:
  `use <new> instead of <old>`;
- `REPLACE_NEW` and `REPLACE_OLD` are raw substrings with no quote-aware or
  escape-aware parsing;
- neither operand may contain the exact delimiter ` instead of `.

Canonical parsed meaning:

- remove the old policy item from active use;
- assert the new policy item as `use`;
- semantic validity still depends on authoritative state.

Malformed examples:

- `use podman instead of`
- `use instead of docker`
- `use  instead of docker`

Invalid alternate phrasings:

- `replace docker with podman`
- `switch from docker to podman`
- `use podman rather than docker`

### 7.4 Administrative commands

These productions take no operands and must match exactly:

```text
CLEAR_PREMISE  := "clear premise"
RESET_POLICIES := "reset policies"
CLEAR_STATE    := "clear state"
```

Malformed examples:

- <code>clear premise </code>
- `reset policies now`
- `clear state then continue`

### 7.5 Compound-attempt rejection

The canonical language permits at most one directive attempt per input.

An input is directive-shaped invalid input, not a canonical directive, if it
contains more than one attempted directive clause. This includes inputs such
as:

- `use docker and prohibit peanuts`
- `set premise project deadline is Friday and use docker` is one premise directive; `VALUE` is
  opaque and may contain policy words or conjunctions.
- `clear state then set premise new project`

This rule is lexical and grammar-level. It is not a semantic conflict rule.

Premise `VALUE` is payload rather than a policy identity. The grammar does not
inspect embedded directive words, conjunctions, or sentence boundaries inside
it. A separate canonical directive beginning on a new line is still treated as
a compound attempt. `ITEM` operands retain the compound-detection behavior
described above.

Examples:

- no_directive: `"use docker and prohibit peanuts"`
- directive-shaped invalid: `use "docker and prohibit peanuts"`
- canonical directive: `set premise "use docker and prohibit peanuts"`

## 8. Parsed Meaning and Semantic Boundary

This section separates successful parsing from state-dependent evaluation.

### 8.1 Syntax validity

Syntax validity depends only on Sections 6 and 7.

Syntax validity does not inspect:

- current premise state;
- current policy state;
- contradictions;
- replacement preconditions.

### 8.2 Semantic evaluation

Only a successfully parsed canonical directive proceeds to semantic evaluation.

Semantic evaluation may produce:

- apply
- no-op update
- `error`

`error` is reserved for state-dependent conflicts or precondition failures of
an already parsed canonical directive.

Every semantic `error` is a terminal result for the current input. It leaves
authoritative state unchanged and returns the failure classification, failed
canonical directive, ordered advisory repairs, and presentation message.
Recovery is possible only when the host explicitly selects and submits a
returned repair through `apply_directive(...)`.

An absent source item in a canonical replacement directive is a state-fact
mismatch. If `use <new> instead of <old>` parses canonically and `<old>` is
absent from authoritative state, the result is a semantic `error` and the
operation is not degraded to plain `use <new>`.

### 8.3 Family-by-family semantic boundary

- `set premise <value>`
  - syntax: canonical only if Section 7.1 matches exactly
  - semantic precondition: premise is currently `null`
  - possible outcomes: apply, `error`

- `change premise to <value>`
  - syntax: canonical only if Section 7.1 matches exactly
  - semantic precondition: premise is currently non-`null`
  - possible outcomes: apply, `error`

- `use <item>`
  - syntax: canonical only if Section 7.2 matches exactly
  - semantic precondition: item is not currently prohibited
  - possible outcomes: apply, no-op update, `error`

- `prohibit <item>`
  - syntax: canonical only if Section 7.2 matches exactly
  - semantic precondition: item is not currently in use
  - possible outcomes: apply, no-op update, `error`

- `remove policy <item>`
  - syntax: canonical only if Section 7.2 matches exactly
  - semantic precondition: none
  - possible outcomes: apply, no-op update

- `use <new> instead of <old>`
  - syntax: canonical only if Section 7.3 matches exactly
  - semantic preconditions: replacement-specific state rules
  - possible outcomes: apply, no-op update, `error`

- `clear premise`, `reset policies`, `clear state`
  - syntax: exact literal only
  - semantic precondition: none
  - possible outcomes: apply, no-op update

Malformed syntax never reaches these semantic paths.

## 9. State-Dependent Semantics

This section summarizes the semantic boundary relevant to grammar.

### 9.1 Policy operand identity

For policy-bearing directives, parsed operand text is preserved at parse time,
but semantic evaluation does not compare policy operands by exact submitted
spelling.

For these directive families:

- `use <item>`
- `prohibit <item>`
- `remove policy <item>`
- `use <new> instead of <old>`

policy operand identity is determined by the canonical policy key produced by
the storage normalization rules in Section 10.1.

For policy state, authoritative storage uses the canonical policy identity key
rather than the original submitted operand spelling.

Observable consequences:

- policy comparison is case-insensitive;
- repeated internal whitespace does not create a distinct policy identity;
- canonical-equivalent or compatibility-equivalent Unicode forms that produce
  the same NFKC value do not create a distinct policy identity;
- accent differences that remain after NFKC, such as `cafe` and `café`, remain
  distinct policy identities;
- Unicode casefold mappings are applied, including `ſ` with `s`, `ß` with
  `ss`, and Greek final sigma `ς` with `σ`;
- equivalent apostrophe characters normalized by Section 10.1 do not create a
  distinct policy identity.

Semantic checks that depend on policy identity include:

- contradiction checks for `use` vs `prohibit`;
- idempotence checks for repeated `use` or `prohibit`;
- lookup and removal for `remove policy`;
- source/target identity comparison and state lookup for replacement.

This is a semantic identity rule, not a parsing rule.

### 9.2 Premise lifecycle

- `set premise X`
  - apply when no premise exists
  - `error` when a premise already exists

- `change premise to X`
  - apply when a premise exists
  - `error` when no premise exists

Premise lifecycle is slot-based, not operand-identity based.

This specification does not define a policy-style identity key for premise
values.

### 9.3 Policy lifecycle

Let `k` be the policy identity key for `ITEM` under Section 10.1.

- `use ITEM`
  - apply when `k` is absent
  - no-op update when `policies[k] == "use"`
  - `error` when `policies[k] == "prohibit"`

- `prohibit ITEM`
  - apply when `k` is absent
  - no-op update when `policies[k] == "prohibit"`
  - `error` when `policies[k] == "use"`

- `remove policy ITEM`
  - remove `k` when present
  - no-op update when absent

### 9.4 Replacement

Let `kx` be the policy identity key for `REPLACE_NEW` under Section 10.1 and
`ky` be the policy identity key for `REPLACE_OLD` under Section 10.1.

- replacement parses independently of state;
- semantic evaluation may still reject the operation with `error`;
- replacement is not a repair mechanism for malformed input;
- replacement is not a natural-language correction surface.

The replacement-specific `error` cases are state-dependent and belong to
semantic evaluation, not parsing.

Normative classification for the missing-source case:

- if `ky` is absent, `use <new> instead of <old>` is an `error` case;
- replacement requires an active existing `use` policy for `REPLACE_OLD`;
- core must not degrade the canonical replacement directive into plain
  `use <new>`;
- malformed replacement syntax remains invalid grammar, and other semantic
  conflicts for a canonical replacement may still return `error`.

### 9.5 Clarify rule

Core returns `error` only after:

1. canonical parsing succeeds; and
2. semantic evaluation finds a state conflict or state-dependent precondition
   failure.

Malformed, incomplete, near-canonical, and compound directive-shaped inputs are
outside this category.

## 10. Storage Normalization

Normalization below applies after successful parsing, during storage or lookup.
It is not part of syntax repair.

### 11.1 Policy identity

Policy-bearing directives derive a canonical policy identity for storage,
lookup, and semantic comparison.

Policy identity currently uses:

- Unicode NFKC normalization: yes
- apostrophe-character normalization (for example `’` to `'`): yes
- Unicode default full case folding: yes
- internal whitespace collapse: yes
- article removal: no
- spelling correction: no
- contraction expansion: no
- rewriting `dont` to `don't`: no
- synonym matching: no
- natural-language equivalence: no

Normalization order for policy identity is:

1. Unicode NFKC normalization
2. apostrophe-character normalization
3. Unicode default full case folding
4. internal whitespace collapse

For Python implementations, Step 3 corresponds to `str.casefold()`.
Ordinary lowercasing is not sufficient.

The `yes` entries above are representation canonicalization. They do not
authorize natural-language interpretation of different wordings as the same
policy item.

For imported persisted state, if two distinct input policy keys normalize to
the same canonical policy identity key, the payload is invalid and must be
rejected atomically. Core must not resolve such collisions by selecting one
input value and silently discarding the other.

If a future version intentionally introduces broader policy-identity semantics,
that behavior must be specified explicitly.

Acquisition-layer note:

- language-specific or semantic normalization beyond the representation-level
  rules above belongs outside core;
- examples include leading-article removal, rewriting `dont` to `don't`, and
  other broader human-input interpretation behaviors.

### 11.2 Premise-value sanitation

Premise values are stored as semantically opaque strings with
representation-level sanitation only:

1. Unicode normalization
2. apostrophe normalization
3. whitespace collapse

After this sanitation:

- an empty resulting premise value is invalid for persisted state and must be
  rejected atomically rather than stored as `""`
- premise sanitation is representation-level only; it does not create a
  premise-identity system analogous to policy identity

No stemming, synonym mapping, ontology, or semantic rewriting is allowed.

## 11. Normative Example Matrix

These examples are normative illustrations of the contract and are suitable
source material for later conformance fixtures.

| Input | Classification | Parsed operation | Semantic note |
| --- | --- | --- | --- |
| `set premise project deadline is Friday` | canonical directive | set premise | may apply or error depending on premise state |
| `change premise to project deadline is Thursday` | canonical directive | change premise | may apply or error depending on premise state |
| `use docker` | canonical directive | use item | may apply, no-op, or error |
| `use Docker` | canonical directive | use item | same policy identity as `use docker` |
| `prohibit Docker` after `use docker` | canonical directive | prohibit item | same policy identity triggers contradiction |
| `use don’t` | canonical directive | use item | may share policy identity with `use don't` as representation normalization |
| `use don't` | canonical directive | use item | apostrophe-character variants do not require a distinct policy identity |
| `prohibit peanuts` | canonical directive | prohibit item | may apply, no-op, or error |
| `remove policy docker` | canonical directive | remove policy | may apply or no-op |
| `use podman instead of docker` | canonical directive | replace use | may apply, no-op, or error |
| `use podman instead of docker` when `docker` is absent | canonical directive | replace use | semantic error; replacement requires an active source `use` policy |
| `clear premise` | canonical directive | clear premise | may apply or no-op |
| `reset policies` | canonical directive | reset policies | may apply or no-op |
| `clear state` | canonical directive | clear state | may apply or no-op |
| `hello there` | no_directive | none | not directive-shaped |
| `Use docker` | canonical directive | use item | keyword case is normalized |
| `"use docker"` | no_directive | none | quoted wrapper has no directive semantics |
| `allow docker` | no_directive | none | alias is outside canonical grammar |
| `use\tdocker` | canonical directive | use item | tab normalizes to canonical separator |
| <code> use docker </code> | canonical directive | use item | boundary ASCII whitespace is trimmed |
| `Use    Docker` | canonical directive | use item | keyword and separator presentation normalize; operand text remains `Docker` |
| `use dont` | canonical directive | use item | semantic equivalence to `use don't` is not guaranteed by this specification |
| `use the docker instead of docker` | canonical directive | replace use | semantic equivalence to `docker` is not guaranteed by this specification |
| `set premise` | directive-shaped invalid input | none | incomplete |
| `change premise to` | directive-shaped invalid input | none | incomplete |
| `use` | directive-shaped invalid input | none | incomplete |
| `prohibit` | directive-shaped invalid input | none | incomplete |
| `remove policy` | directive-shaped invalid input | none | incomplete |
| `use podman instead of` | directive-shaped invalid input | none | incomplete replacement |
| `use instead of docker` | directive-shaped invalid input | none | incomplete replacement |
| `set premise to concise` | directive-shaped invalid input | none | unexpected keyword is not removed |
| `use docker and prohibit peanuts` | directive-shaped invalid input | none | compound attempt |
| `clear state then set premise project` | directive-shaped invalid input | none | compound attempt |
| `use "docker and prohibit peanuts"` | directive-shaped invalid input | none | quotes do not protect embedded directive text |
| `set premise "use docker and prohibit peanuts"` | canonical directive | set premise | premise `VALUE` is opaque payload, including quote characters |

## 12. Invariants

1. State changes only from canonical directives that pass semantic evaluation.
2. Same input sequence yields identical state and decisions.
3. LLM output never mutates authoritative state.
4. `error` is semantic, not syntactic.
5. A single input never applies more than one canonical directive.
6. Core does not repair non-canonical human input into canonical directives.
7. A semantic `error` is terminal for the current input and leaves authoritative
   state unchanged.
8. Repairs are canonical, ordered, advisory directives and are never applied
   automatically.
9. Hosts explicitly select and submit any repair through `apply_directive(...)`.

## 13. Non-Goals

Not part of the current core grammar:

- natural-language aliases;
- malformed-input recovery;
- implicit operands;
- quoting or escaping syntax;
- multiple directives in one input;
- implicit runtime recovery state;
- entity modeling;
- ordered policy history;
- readonly or locked-state modifiers.
