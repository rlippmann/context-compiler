"""Example 8: inspect structured decisions at both engine boundaries."""

from context_compiler import (
    Decision,
    Engine,
    NoDirectiveDecision,
    SemanticErrorDecision,
    UpdateDecision,
)
from context_compiler.grammar import CanonicalDirective, DirectiveKind, decompose_directive


def print_decision(decision: Decision) -> None:
    if isinstance(decision, NoDirectiveDecision):
        print(f"NoDirectiveDecision.kind: {decision.kind}")
        return

    if isinstance(decision, UpdateDecision):
        print(f"UpdateDecision.changed: {decision.changed}")
        return

    assert isinstance(decision, SemanticErrorDecision)
    print(f"SemanticErrorDecision.failure: {decision.failure}")
    print(f"SemanticErrorDecision.directive: {decision.directive.text}")
    print("SemanticErrorDecision.repairs: " + ", ".join(repair.text for repair in decision.repairs))
    print(f"SemanticErrorDecision.message: {decision.message}")


def handle_step(engine: Engine, raw_input: str) -> Decision:
    print(f"step raw input: {raw_input}")
    decision = engine.step(raw_input)
    print_decision(decision)
    return decision


def apply_canonical_directive(
    engine: Engine, directive: CanonicalDirective
) -> UpdateDecision | SemanticErrorDecision:
    print(f"CanonicalDirective: {directive.text}")
    decision = engine.apply_directive(directive)
    print_decision(decision)
    assert isinstance(decision, UpdateDecision | SemanticErrorDecision)
    return decision


def main() -> None:
    print("engine.step() raw input boundary:")
    step_engine = Engine()
    handle_step(step_engine, "hello there")
    handle_step(step_engine, "prohibit docker")
    handle_step(step_engine, "use docker")

    print("terminal semantic error follow-up:")
    followup_engine = Engine()
    before = (followup_engine.premise, dict(followup_engine.policies))
    replacement_error = followup_engine.step("use podman instead of docker")
    assert isinstance(replacement_error, SemanticErrorDecision)
    after_error = (followup_engine.premise, dict(followup_engine.policies))
    assert after_error == before
    print("State unchanged after missing-source replacement: True")
    print("No repair or continuation applied automatically.")

    followup = followup_engine.step("yes")
    assert isinstance(followup, NoDirectiveDecision)
    print("Later unrelated input: NoDirectiveDecision")
    print()

    print("decompose_directive() + engine.apply_directive() canonical boundary:")
    apply_engine = Engine()

    directive = decompose_directive("prohibit docker")
    assert isinstance(directive, CanonicalDirective)
    apply_canonical_directive(apply_engine, directive)

    directive = decompose_directive("use docker")
    assert isinstance(directive, CanonicalDirective)
    error = apply_canonical_directive(apply_engine, directive)
    assert isinstance(error, SemanticErrorDecision)

    if error.repairs:
        print("Applying selected repairs:")
        remove_policy_repair = next(
            repair for repair in error.repairs if repair.kind is DirectiveKind.REMOVE_POLICY
        )
        retry_use_repair = next(
            repair for repair in error.repairs if repair.kind is DirectiveKind.USE_ITEM
        )
        print(f"Selected repair: {remove_policy_repair.text}")
        apply_canonical_directive(apply_engine, remove_policy_repair)
        print(f"Selected repair: {retry_use_repair.text}")
        apply_canonical_directive(apply_engine, retry_use_repair)


if __name__ == "__main__":
    main()
