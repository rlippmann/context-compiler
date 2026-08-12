import context_compiler
import context_compiler.grammar as grammar_module


def test_root_does_not_export_public_grammar_surface() -> None:
    for name in (
        "DirectiveKind",
        "DirectiveSyntaxFailure",
        "CanonicalDirective",
        "InvalidDirectiveSyntax",
        "decompose_directive",
    ):
        assert name not in context_compiler.__all__
        assert not hasattr(context_compiler, name)


def test_grammar_submodule_preserves_public_grammar_surface() -> None:
    assert grammar_module.DirectiveKind is not None
    assert grammar_module.DirectiveSyntaxFailure is not None
    assert grammar_module.CanonicalDirective is not None
    assert grammar_module.InvalidDirectiveSyntax is not None
    assert grammar_module.decompose_directive is not None
    assert not hasattr(grammar_module, "render_directive")
    assert not hasattr(grammar_module, "contains_multiple_canonical_directives")
    assert not hasattr(grammar_module, "match_canonical_directive_start")


def test_root_does_not_export_private_grammar_implementation() -> None:
    for name in (
        "_DIRECTIVE_SPECS",
        "_SET_PREMISE_RE",
        "_CHANGE_PREMISE_RE",
        "_USE_RE",
        "_PROHIBIT_RE",
        "_REMOVE_POLICY_RE",
        "_REPLACE_RE",
        "_match_directive_token",
        "_match_canonical_directive_start",
    ):
        assert name not in context_compiler.__all__
        assert not hasattr(context_compiler, name)
