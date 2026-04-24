import pytest

from experimental.preprocessor.heuristic_precompiler import precompile_heuristic


def test_heuristic_rejects_consistent_high_risk_non_directives() -> None:
    cases = [
        "allow docker",
        "set policy peanuts prohibit",
        "stop using peanuts",
        "use instead of docker",
        "use podman instead of",
        "use podman not docker",
        "wipe policies",
        "clear premise then clear state",
        "prohibit peanuts and use almonds",
        "set premise concise; reset policies",
        "use docker, actually prohibit docker",
        '"set premise concise replies" is invalid syntax, right?',
        'For example, you could "remove policy docker".',
        'He said "use docker".',
        'The doc literally says: "clear premise".',
    ]

    for message in cases:
        result = precompile_heuristic(message)
        assert result["outcome"] == "unknown"
        assert result["directive"] is None
        assert result["rule_id"] is not None


def test_heuristic_accepts_trailing_period_or_bang_for_whole_message_directives() -> None:
    cases = [
        ("clear state.", "clear state"),
        ("reset policies!", "reset policies"),
        ("use docker.", "use docker"),
    ]
    for message, expected in cases:
        assert precompile_heuristic(message) == {
            "outcome": "directive",
            "directive": expected,
            "rule_id": "canonical.full_match",
        }


def test_heuristic_allows_exact_full_message_wrappers_for_directives() -> None:
    cases = [
        ("(reset policies)", "reset policies"),
        ("[prohibit peanuts]", "prohibit peanuts"),
    ]
    for message, expected in cases:
        assert precompile_heuristic(message) == {
            "outcome": "directive",
            "directive": expected,
            "rule_id": "canonical.full_match",
        }


def test_heuristic_rejects_quoted_or_backticked_exact_directives() -> None:
    cases = [
        "`use docker`",
        '"clear state"',
        "'reset policies'",
    ]
    for message in cases:
        assert precompile_heuristic(message) == {
            "outcome": "unknown",
            "directive": None,
            "rule_id": "reject.quoted_exact",
        }


def test_heuristic_case_normalizes_exact_command_shapes() -> None:
    cases = [
        ("CLEAR STATE", "clear state"),
        ("Use Docker", "use docker"),
        ("Prohibit Peanuts", "prohibit peanuts"),
    ]
    for message, expected in cases:
        assert precompile_heuristic(message) == {
            "outcome": "directive",
            "directive": expected,
            "rule_id": "canonical.full_match",
        }


def test_heuristic_question_mark_only_non_directive_is_confident() -> None:
    assert precompile_heuristic("can you help with lunch?") == {
        "outcome": "no_directive",
        "directive": None,
        "rule_id": "reject.confident_non_directive",
    }


def test_heuristic_rejects_directive_adjacent_question_mark_as_unknown() -> None:
    cases = [
        "use docker?",
        "clear state?",
        "can you use pytest instead of unittest?",
    ]
    for message in cases:
        result = precompile_heuristic(message)
        assert result["outcome"] == "unknown"
        assert result["directive"] is None
        assert result["rule_id"] is not None


def test_heuristic_rejects_meta_reporting_or_example_prefixes() -> None:
    cases = [
        "example: use docker",
        "the command is clear state",
        'I said "use docker"',
        'he said "reset policies"',
        'example: "use docker"',
    ]
    for message in cases:
        assert precompile_heuristic(message) == {
            "outcome": "unknown",
            "directive": None,
            "rule_id": "reject.meta_or_reporting",
        }


def test_heuristic_rejects_list_or_enumeration_inputs() -> None:
    cases = [
        "1. use docker",
        "- clear state",
        "* prohibit peanuts",
    ]
    for message in cases:
        assert precompile_heuristic(message) == {
            "outcome": "unknown",
            "directive": None,
            "rule_id": "reject.list_or_enumeration",
        }


def test_heuristic_rejects_multi_segment_or_mixed_prose_inputs() -> None:
    cases = [
        "use docker because this repo already has Docker",
        "clear state then continue",
        "use docker and prohibit peanuts",
    ]
    for message in cases:
        assert precompile_heuristic(message) == {
            "outcome": "unknown",
            "directive": None,
            "rule_id": "reject.multi_segment_or_mixed_prose",
        }


def test_heuristic_rejects_malformed_replacement_syntax() -> None:
    cases = [
        "use podman instead docker",
        "use podman in stead of docker",
    ]
    for message in cases:
        assert precompile_heuristic(message) == {
            "outcome": "unknown",
            "directive": None,
            "rule_id": "reject.malformed_replacement_syntax",
        }


def test_heuristic_rejects_admin_near_miss_aliases() -> None:
    cases = [
        "reset policy",
        "remove policies docker",
    ]
    for message in cases:
        assert precompile_heuristic(message) == {
            "outcome": "unknown",
            "directive": None,
            "rule_id": "reject.admin_near_miss_alias",
        }


def test_heuristic_rejects_notes_and_reporting_with_bracketed_mentions() -> None:
    cases = [
        "In my notes: [clear state] [reset policies]",
        "Notes: [use docker] [prohibit peanuts]",
        "I wrote down [change premise to concise replies] yesterday",
    ]
    for message in cases:
        assert precompile_heuristic(message) == {
            "outcome": "unknown",
            "directive": None,
            "rule_id": "reject.quoted_reported_bracket",
        }


def test_heuristic_accepts_bracket_wrapper_without_reporting_marker() -> None:
    assert precompile_heuristic("[clear state]") == {
        "outcome": "directive",
        "directive": "clear state",
        "rule_id": "canonical.full_match",
    }


def test_heuristic_set_premise_to_forms_are_unknown_not_rewritten() -> None:
    cases = [
        "set premise to concise replies",
        "set premise to formal tone",
    ]
    for message in cases:
        assert precompile_heuristic(message) == {
            "outcome": "unknown",
            "directive": None,
            "rule_id": "reject.directive_adjacent_unsafe",
        }


def test_heuristic_dont_use_forms_are_unknown_not_rewritten() -> None:
    cases = [
        "don't use peanuts",
        "do not use peanuts",
    ]
    for message in cases:
        assert precompile_heuristic(message) == {
            "outcome": "unknown",
            "directive": None,
            "rule_id": "reject.directive_adjacent_unsafe",
        }


def test_heuristic_does_not_canonicalize_set_premise_to_with_empty_payload() -> None:
    assert precompile_heuristic("set premise to   ") == {
        "outcome": "unknown",
        "directive": None,
        "rule_id": "reject.directive_adjacent_unsafe",
    }


def test_heuristic_does_not_canonicalize_set_premise_to_when_not_whole_message() -> None:
    assert precompile_heuristic("please set premise to concise replies") == {
        "outcome": "unknown",
        "directive": None,
        "rule_id": "reject.directive_adjacent_unsafe",
    }


def test_heuristic_change_premise_missing_to_forms_are_unknown_not_rewritten() -> None:
    cases = [
        "change premise concise replies",
        "change premise formal tone",
    ]
    for message in cases:
        assert precompile_heuristic(message) == {
            "outcome": "unknown",
            "directive": None,
            "rule_id": "reject.directive_adjacent_unsafe",
        }


def test_heuristic_does_not_canonicalize_change_premise_with_empty_payload() -> None:
    assert precompile_heuristic("change premise   ") == {
        "outcome": "unknown",
        "directive": None,
        "rule_id": "reject.directive_adjacent_unsafe",
    }


def test_heuristic_does_not_canonicalize_change_premise_when_not_whole_message() -> None:
    assert precompile_heuristic("please change premise concise replies") == {
        "outcome": "unknown",
        "directive": None,
        "rule_id": "reject.directive_adjacent_unsafe",
    }


def test_heuristic_accepts_strict_canonical_directives() -> None:
    directives = [
        "set premise concise replies",
        "change premise to concise replies",
        "use docker",
        "prohibit peanuts",
        "remove policy docker",
        "use podman instead of docker",
        "clear premise",
        "reset policies",
        "clear state",
    ]

    for directive in directives:
        result = precompile_heuristic(directive)
        assert result == {
            "outcome": "directive",
            "directive": directive,
            "rule_id": "canonical.full_match",
        }


def test_heuristic_returns_unknown_for_unresolved_cases() -> None:
    unresolved = ["Could we maybe use uv later"]

    for message in unresolved:
        assert precompile_heuristic(message) == {
            "outcome": "unknown",
            "directive": None,
            "rule_id": "reject.directive_adjacent_unsafe",
        }


def test_heuristic_returns_no_directive_for_ordinary_non_directive_content() -> None:
    cases = [
        "not sure this is right",
        "thanks for the help",
    ]
    for message in cases:
        assert precompile_heuristic(message) == {
            "outcome": "no_directive",
            "directive": None,
            "rule_id": "reject.confident_non_directive",
        }


@pytest.mark.parametrize("message", ['""', "''", "()", "[]", "``"])
def test_heuristic_empty_wrappers_do_not_produce_directive(message: str) -> None:
    result = precompile_heuristic(message)
    assert result["directive"] is None
