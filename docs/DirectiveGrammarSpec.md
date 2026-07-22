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

`clarify` is a semantic outcome, not a parsing category.

## 2. System Responsibilities

The compiler:

1. Classifies raw input using the rules in Sections 5 and 6.
2. Parses canonical directives using the grammar in Section 7.
3. Performs semantic evaluation only after successful canonical parsing.
4. Applies deterministic state transitions only for semantically valid canonical directives.
5. Returns a deterministic `Decision`.

The compiler never calls an LLM.
All authoritative mutations originate from canonical user directives passed to
`step()`.

## 3. Host Responsibilities

The host:

- handles `passthrough` input outside core;
- displays clarification prompts when core returns `clarify`;
- calls the LLM only when the returned `Decision.kind` allows it;
- may perform non-canonical drafting or repair before calling core.

## 4. Decision API Contract

```python
class Decision(TypedDict):
    kind: Literal["passthrough", "update", "clarify"]
    state: dict | None
    prompt_to_user: str | None
```

Semantics:

- `passthrough`: forward user input to the host/model path
- `update`: canonical directive parsed and semantic evaluation completed without
  a blocking conflict
- `clarify`: canonical directive parsed, but semantic evaluation could not
  safely execute under current authoritative state

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

Before classifying raw input as passthrough, directive-shaped invalid input, or
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

1. `passthrough`
2. directive-shaped invalid input
3. canonical directive

### 6.3 Passthrough

Input is `passthrough` when it does not begin with a canonical directive
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
`clarify`.

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
- has no quote-aware or escape-aware subgrammar;
- is rejected if the full input would otherwise constitute a compound attempt
  under Section 7.5.

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
- `set premise vegetarian and use docker`
- `clear state then set premise new project`

This rule is lexical and grammar-level. It is not a semantic conflict rule.

The grammar does not define quoting or escaping syntax to protect embedded
directive text inside operands. Therefore, if raw input both begins like a
directive attempt and later contains another directive attempt, the full input
is outside the canonical language.

Examples:

- passthrough: `"use docker and prohibit peanuts"`
- directive-shaped invalid: `use "docker and prohibit peanuts"`
- directive-shaped invalid: `set premise "use docker and prohibit peanuts"`

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
- `clarify`

`clarify` is reserved for state-dependent conflicts or precondition failures of
an already parsed canonical directive.

### 8.3 Family-by-family semantic boundary

- `set premise <value>`
  - syntax: canonical only if Section 7.1 matches exactly
  - semantic precondition: premise is currently `null`
  - possible outcomes: apply, `clarify`

- `change premise to <value>`
  - syntax: canonical only if Section 7.1 matches exactly
  - semantic precondition: premise is currently non-`null`
  - possible outcomes: apply, `clarify`

- `use <item>`
  - syntax: canonical only if Section 7.2 matches exactly
  - semantic precondition: item is not currently prohibited
  - possible outcomes: apply, no-op update, `clarify`

- `prohibit <item>`
  - syntax: canonical only if Section 7.2 matches exactly
  - semantic precondition: item is not currently in use
  - possible outcomes: apply, no-op update, `clarify`

- `remove policy <item>`
  - syntax: canonical only if Section 7.2 matches exactly
  - semantic precondition: none
  - possible outcomes: apply, no-op update

- `use <new> instead of <old>`
  - syntax: canonical only if Section 7.3 matches exactly
  - semantic preconditions: replacement-specific state rules
  - possible outcomes: apply, no-op update, `clarify`

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
  - `clarify` when a premise already exists

- `change premise to X`
  - apply when a premise exists
  - `clarify` when no premise exists

Premise lifecycle is slot-based, not operand-identity based.

This specification does not define a policy-style identity key for premise
values.

### 9.3 Policy lifecycle

Let `k` be the policy identity key for `ITEM` under Section 10.1.

- `use ITEM`
  - apply when `k` is absent
  - no-op update when `policies[k] == "use"`
  - `clarify` when `policies[k] == "prohibit"`

- `prohibit ITEM`
  - apply when `k` is absent
  - no-op update when `policies[k] == "prohibit"`
  - `clarify` when `policies[k] == "use"`

- `remove policy ITEM`
  - remove `k` when present
  - no-op update when absent

### 9.4 Replacement

Let `kx` be the policy identity key for `REPLACE_NEW` under Section 10.1 and
`ky` be the policy identity key for `REPLACE_OLD` under Section 10.1.

- replacement parses independently of state;
- semantic evaluation may still reject the operation with `clarify`;
- replacement is not a repair mechanism for malformed input;
- replacement is not a natural-language correction surface.

The replacement-specific `clarify` cases are state-dependent and belong to
semantic evaluation, not parsing.

### 9.5 Clarify rule

Core returns `clarify` only after:

1. canonical parsing succeeds; and
2. semantic evaluation finds a state conflict or state-dependent precondition
   failure.

Malformed, incomplete, near-canonical, and compound directive-shaped inputs are
outside this category.

## 10. Storage Normalization

Normalization below applies after successful parsing, during storage or lookup.
It is not part of syntax repair.

### 10.1 Policy identity

Policy-bearing directives derive a canonical policy identity for storage,
lookup, and semantic comparison.

Policy identity currently uses:

- Unicode NFKC normalization: yes
- apostrophe-character normalization (for example `’` to `'`): yes
- case folding: yes
- internal whitespace collapse: yes
- article removal: no
- spelling correction: no
- contraction expansion: no
- rewriting `dont` to `don't`: no
- synonym matching: no
- natural-language equivalence: no

The `yes` entries above are representation canonicalization. They do not
authorize natural-language interpretation of different wordings as the same
policy item.

If a future version intentionally introduces broader policy-identity semantics,
that behavior must be specified explicitly.

Repository drift note:

- the current runtime implementation still performs additional item-key
  rewrites beyond the normative boundary above, including leading-article
  removal and `dont` to `don't` rewriting;
- those behaviors are current implementation details and test-backed runtime
  behavior, but they are not frozen here as the intended core semantic contract.

### 10.2 Premise-value sanitation

Premise values are stored as semantically opaque strings with
representation-level sanitation only:

1. Unicode normalization
2. apostrophe normalization
3. whitespace collapse

No stemming, synonym mapping, ontology, or semantic rewriting is allowed.

## 11. Non-Current Pending Confirmation Language

The current intended core grammar contract does not add or rely on pending
confirmation behavior.

Repository code may still expose checkpoint fields or helper APIs that mention
pending continuation for compatibility reasons, but pending confirmation is not
part of the current directive grammar contract defined here.

This specification therefore does not define:

- confirmation tokens as grammar input;
- pending-only parsing mode;
- pending-only semantic continuation rules.

If future work reintroduces reachable pending continuation semantics, that
behavior must be specified separately and must not redefine malformed syntax as
confirmable canonical input.

## 12. Normative Example Matrix

These examples are normative illustrations of the contract and are suitable
source material for later conformance fixtures.

| Input | Classification | Parsed operation | Semantic note |
| --- | --- | --- | --- |
| `set premise concise replies` | canonical directive | set premise | may apply or clarify depending on premise state |
| `change premise to concise replies` | canonical directive | change premise | may apply or clarify depending on premise state |
| `use docker` | canonical directive | use item | may apply, no-op, or clarify |
| `use Docker` | canonical directive | use item | same policy identity as `use docker` |
| `prohibit Docker` after `use docker` | canonical directive | prohibit item | same policy identity triggers contradiction |
| `use don’t` | canonical directive | use item | may share policy identity with `use don't` as representation normalization |
| `use don't` | canonical directive | use item | apostrophe-character variants do not require a distinct policy identity |
| `prohibit peanuts` | canonical directive | prohibit item | may apply, no-op, or clarify |
| `remove policy docker` | canonical directive | remove policy | may apply or no-op |
| `use podman instead of docker` | canonical directive | replace use | may apply, no-op, or clarify |
| `clear premise` | canonical directive | clear premise | may apply or no-op |
| `reset policies` | canonical directive | reset policies | may apply or no-op |
| `clear state` | canonical directive | clear state | may apply or no-op |
| `hello there` | passthrough | none | not directive-shaped |
| `Use docker` | canonical directive | use item | keyword case is normalized |
| `"use docker"` | passthrough | none | quoted wrapper has no directive semantics |
| `allow docker` | passthrough | none | alias is outside canonical grammar |
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
| `set premise "use docker and prohibit peanuts"` | directive-shaped invalid input | none | quotes do not protect embedded directive text |

## 13. Invariants

1. State changes only from canonical directives that pass semantic evaluation.
2. Same input sequence yields identical state and decisions.
3. LLM output never mutates authoritative state.
4. `clarify` is semantic, not syntactic.
5. A single input never applies more than one canonical directive.
6. Core does not repair non-canonical human input into canonical directives.

## 14. Non-Goals

Not part of the current core grammar:

- natural-language aliases;
- malformed-input recovery;
- implicit operands;
- quoting or escaping syntax;
- multiple directives in one input;
- entity modeling;
- ordered policy history;
- pending-confirmation grammar;
- readonly or locked-state modifiers.
