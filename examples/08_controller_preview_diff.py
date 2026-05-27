"""Example 8: controller preview + state diff + apply flow."""

from _util import print_decision_summary, print_state_summary

from context_compiler import create_engine, preview, state_diff, step


def main() -> None:
    engine = create_engine()

    state_before = engine.state
    print_state_summary(state_before, "state before preview")

    print("\nPreview: prohibit peanuts")
    preview_result = preview(engine, "prohibit peanuts")
    print("would_mutate:", preview_result["would_mutate"])
    print_decision_summary(preview_result["decision"])

    state_after_preview = engine.state
    diff_after_preview = state_diff(state_before, state_after_preview)
    print("state changed after preview:", diff_after_preview["changed"])

    print("\nApply: prohibit peanuts")
    step_result = step(engine, "prohibit peanuts")
    print_decision_summary(step_result["decision"])
    print_state_summary(step_result["state"], "state after step")


if __name__ == "__main__":
    main()
