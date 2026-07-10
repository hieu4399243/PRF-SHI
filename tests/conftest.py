import pytest
import app as app_module


@pytest.fixture(autouse=True)
def _reset_rate_buckets():
    app_module._RATE_BUCKETS.clear()
    yield
    app_module._RATE_BUCKETS.clear()
