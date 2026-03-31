EVALUATION RUBRIC (STRICT — DO NOT MODIFY)

Harness note:
`manual_compiled_prompt` is a handwritten, state-framed comparison prompt.
It is NOT produced by Context Compiler.

All tasks must be scored using this rubric exactly.

Weights:

* Correct fix locus = 2
* Constraint fidelity = 3
* Constraint-dependent reasoning correctness = 5
* Scope control = 2
* Backward-compat reasoning = 2
* Test specificity = 3
* Risk analysis quality = 1
* Internal consistency = 2
* Policy traceability = 1
* Anti-genericity = 3

Definitions:

Correct fix locus:
Does the answer identify the correct subsystem or conceptual location of the bug?

Constraint fidelity:
Does the answer respect all stated constraints and invariants?

Constraint-dependent reasoning correctness:
Does the compiled prompt materially improve the reasoning path, not just structure?
This is the most important criterion.

Scope control:
Does the solution remain minimal and avoid unrelated refactoring?

Backward-compat reasoning:
Does the answer preserve correct behavior outside the bug?

Test specificity:
Are regression tests concrete, relevant, and targeted?

Risk analysis quality:
Are risks realistic and tied to the change?

Internal consistency:
Is the reasoning coherent and non-contradictory?

Policy traceability:
Does the compiled answer explicitly map to constraints?
NOTE: This is low weight and should not dominate scoring.

Anti-genericity:
Does the answer avoid generic bug-pattern guessing and instead reason from the specific problem?

Scoring rules:

* Score baseline and compiled separately.
* Compute weighted totals.
* Compute delta (compiled - baseline).
* Be strict: do not reward formatting or structure unless reasoning improves.
* Penalize generic or speculative reasoning.
* Do not infer intent — score only what is present in the output.

Classification:

* Constraint-critical: reasoning correctness depends on constraints
* Constraint-helpful: constraints improve but are not essential
* Constraint-irrelevant: constraints do not materially affect outcome

Win types:

* structural: reasoning path improved
* formatting: mostly organization/clarity improvement
* mixed: both
* noisy: inconsistent or unclear improvement

Output format:
For each task:

* baseline table
* compiled table
* baseline total
* compiled total
* delta
* classification
* win type
* short justification
