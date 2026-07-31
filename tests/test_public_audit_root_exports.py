import context_compiler
import context_compiler.audit as audit_module


def test_root_does_not_export_public_audit_surface() -> None:
    for name in (
        "PreviewResult",
        "StructuralDiff",
        "diff_has_changes",
        "get_preview_decision",
        "get_preview_state_after",
        "preview",
        "preview_would_mutate",
        "state_diff",
    ):
        assert name not in context_compiler.__all__
        assert not hasattr(context_compiler, name)


def test_audit_submodule_preserves_public_audit_surface() -> None:
    assert audit_module.PreviewResult is not None
    assert audit_module.StructuralDiff is not None
    assert audit_module.diff_has_changes is not None
    assert audit_module.get_preview_decision is not None
    assert audit_module.get_preview_state_after is not None
    assert audit_module.preview is not None
    assert audit_module.preview_would_mutate is not None
    assert audit_module.state_diff is not None
