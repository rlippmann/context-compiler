import pytest

pytestmark = pytest.mark.skip(
    reason="Phase A: examples still encode pre-0.5 semantics; rewrite in Phase B."
)
