import os

# Test phải chạy OFFLINE và cho kết quả tái lập: tắt LLM TRƯỚC khi import app
# (app/storage.py gọi load_dotenv() lúc import, sẽ nạp OPENROUTER_API_KEY từ
# .env thật). Test nào cần LLM thì tự bật lại bằng monkeypatch.
os.environ["LLM_ENABLED"] = "0"

import pytest  # noqa: E402
from app import main as app_module  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_buckets():
    app_module._RATE_BUCKETS.clear()
    yield
    app_module._RATE_BUCKETS.clear()
