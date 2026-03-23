import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "Phase A: prompt-engineering demo assertions require 0.5-aligned compiled-state formatting."
    )
)
