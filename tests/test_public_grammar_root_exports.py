import context_compiler
import context_compiler.grammar as grammar_module


def test_root_reexports_read_only_grammar_contract() -> None:
    assert context_compiler.DirectiveKind is grammar_module.DirectiveKind
    assert context_compiler.validate_directive is grammar_module.validate_directive
    assert context_compiler.render_directive is grammar_module.render_directive
    assert context_compiler.is_canonical_directive is grammar_module.is_canonical_directive


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
        "_parse_directive",
    ):
        assert name not in context_compiler.__all__
        assert not hasattr(context_compiler, name)
