import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from demos.common import consume_last_report  # noqa: E402


def _load_demo_module(filename: str) -> ModuleType:
    module_name = f"test_{filename[:-3]}"
    module_path = REPO_ROOT / "demos" / filename
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_weak_prompt_has_less_guidance_than_strong_prompt() -> None:
    module = _load_demo_module("07_llm_prompt_engineering_comparison.py")

    weak_prompt = module.WEAK_SYSTEM_PROMPT
    strong_prompt = module.STRONG_PROMPT_ENGINEERING_TEXT

    assert "Rules:" not in weak_prompt
    assert "Rules:" in strong_prompt
    assert len(strong_prompt) > len(weak_prompt)


def test_compiler_path_reuses_same_strong_prompt_with_compiled_augmentation() -> None:
    module = _load_demo_module("07_llm_prompt_engineering_comparison.py")
    engine = module.create_engine()
    for user_input in module.USER_INPUTS:
        engine.step(user_input)

    strong_messages = module.build_strong_messages(module.USER_INPUTS)
    compiler_messages = module.build_compiler_messages(engine.state, module.USER_INPUTS)

    compiled_prefix = module.build_compiled_system_prompt(engine.state)
    assert strong_messages[1:] == compiler_messages[1:]
    assert strong_messages[0]["content"] == module.STRONG_PROMPT_ENGINEERING_TEXT
    assert compiler_messages[0]["content"] == (
        f"{compiled_prefix}\n{module.STRONG_PROMPT_ENGINEERING_TEXT}"
    )
    assert compiler_messages[0]["content"].endswith(module.STRONG_PROMPT_ENGINEERING_TEXT)


def test_demo_07_report_semantics_fail_when_weak_not_worse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_demo_module("07_llm_prompt_engineering_comparison.py")
    outputs = iter(
        [
            ("FOCUS_PRIMARY: vegan curry\nShopping list:\n- tofu\n- coconut milk\n- curry paste"),
            ("FOCUS_PRIMARY: vegan curry\nShopping list:\n- tofu\n- coconut milk\n- curry paste"),
            ("FOCUS_PRIMARY: vegan curry\nShopping list:\n- tofu\n- coconut milk\n- curry paste"),
        ]
    )

    def fake_complete_messages(_messages: list[dict[str, str]]) -> str:
        return next(outputs)

    monkeypatch.setattr(module, "complete_messages", fake_complete_messages)
    consume_last_report()
    module.main()
    report = consume_last_report()
    assert report is not None
    assert report["name"] == module.DEMO_NAME
    assert report["baseline_pass"] is True
    assert report["compiler_pass"] is True
    assert report["demo_pass"] is False
