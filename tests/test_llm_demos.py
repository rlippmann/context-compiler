import pytest

pytestmark = pytest.mark.skip(
    reason="Phase A: demo behavior assertions are tied to removed M1 semantics."
)
