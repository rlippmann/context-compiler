"""Example 8: apply canonical directives and inspect structured decisions."""

from context_compiler import Engine, SemanticErrorDecision, UpdateDecision
from context_compiler.grammar import CanonicalDirective, DirectiveKind, decompose_directive


def apply_canonical_directive(
    engine: Engine, directive: CanonicalDirective
) -> UpdateDecision | SemanticErrorDecision:
    print(f"CanonicalDirective: {directive.text}")
    decision = engine.apply_directive(directive)

    if isinstance(decision, UpdateDecision):
        print(f"UpdateDecision.changed: {decision.changed}")
        return decision

    assert isinstance(decision, SemanticErrorDecision)
    print(f"SemanticErrorDecision.failure: {decision.failure}")
    print(f"SemanticErrorDecision.directive: {decision.directive.text}")
    print("SemanticErrorDecision.repairs: " + ", ".join(repair.text for repair in decision.repairs))
    print(f"SemanticErrorDecision.message: {decision.message}")
    return decision


def apply_text_as_canonical_directive(
    engine: Engine, text: str
) -> UpdateDecision | SemanticErrorDecision:
    directive = decompose_directive(text)
    assert isinstance(directive, CanonicalDirective)
    return apply_canonical_directive(engine, directive)


def main() -> None:
    engine = Engine()

    apply_text_as_canonical_directive(engine, "prohibit docker")

    directive = decompose_directive("use docker")
    assert isinstance(directive, CanonicalDirective)
    error = apply_canonical_directive(engine, directive)
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
        apply_canonical_directive(engine, remove_policy_repair)
        print(f"Selected repair: {retry_use_repair.text}")
        apply_canonical_directive(engine, retry_use_repair)


if __name__ == "__main__":
    main()
