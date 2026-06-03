"""Example 8: controller preview + state diff + apply flow."""

from _util import print_decision_summary, print_state_summary

from context_compiler import (
    create_engine,
    diff_has_changes,
    get_preview_decision,
    get_step_decision,
    get_step_state,
    preview,
    preview_would_mutate,
    state_diff,
    step,
)


def main() -> None:
    engine = create_engine()

    state_before = engine.state
    print_state_summary(state_before, "state before preview")

    print("\nPreview: prohibit peanuts")
    preview_result = preview(engine, "prohibit peanuts")
    print("would_mutate:", preview_would_mutate(preview_result))
    print_decision_summary(get_preview_decision(preview_result))

    state_after_preview = engine.state
    diff_after_preview = state_diff(state_before, state_after_preview)
    print("state changed after preview:", diff_has_changes(diff_after_preview))

    print("\nApply: prohibit peanuts")
    step_result = step(engine, "prohibit peanuts")
    print_decision_summary(get_step_decision(step_result))
    print_state_summary(get_step_state(step_result), "state after step")


if __name__ == "__main__":
    main()
