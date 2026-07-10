"""Tests cho cơ chế cap + TTL + LRU eviction của chatbot.SESSIONS (C3)."""

import concurrent.futures
import time

import pytest

from app import chatbot


@pytest.fixture(autouse=True)
def _clean_sessions():
    """Đảm bảo mỗi test bắt đầu với SESSIONS rỗng và khôi phục hằng số sau test."""
    chatbot.SESSIONS.clear()
    yield
    chatbot.SESSIONS.clear()


def test_session_cap_evicts_oldest(monkeypatch):
    monkeypatch.setattr(chatbot, "_MAX_SESSIONS", 5)

    ids = [f"s{i}" for i in range(6)]  # _MAX_SESSIONS + 1
    for sid in ids:
        chatbot.get_session(sid)

    assert len(chatbot.SESSIONS) <= chatbot._MAX_SESSIONS
    assert ids[0] not in chatbot.SESSIONS


def test_session_ttl_expires():
    sid = "ttl-user"
    sess = chatbot.get_session(sid)
    old_state_obj = sess
    sess["state"] = "PICK_DATE"  # marca trạng thái không phải mặc định

    # Đẩy _last_seen về quá khứ xa hơn TTL.
    sess["_last_seen"] = time.time() - chatbot._SESSION_TTL_SECONDS - 1

    refreshed = chatbot.get_session(sid)
    assert refreshed is not old_state_obj
    assert refreshed["state"] == "GREET"


def test_get_session_refreshes_recency(monkeypatch):
    monkeypatch.setattr(chatbot, "_MAX_SESSIONS", 3)

    a_id, b_id = "a", "b"
    chatbot.get_session(a_id)
    chatbot.get_session(b_id)

    # Truy cập lại A -> A trở thành mới nhất.
    chatbot.get_session(a_id)

    # Lấp đầy tới cap: thêm 2 session mới (c, d) sẽ đẩy trần lên 5 > cap=3,
    # evict phải loại bỏ theo thứ tự LRU: B trước, A giữ lại (đã refresh).
    chatbot.get_session("c")
    chatbot.get_session("d")

    assert a_id in chatbot.SESSIONS
    assert b_id not in chatbot.SESSIONS


def test_reset_session_refreshes_recency(monkeypatch):
    monkeypatch.setattr(chatbot, "_MAX_SESSIONS", 3)

    a_id, b_id = "a", "b"
    chatbot.get_session(a_id)
    chatbot.get_session(b_id)

    chatbot.reset_session(a_id)

    chatbot.get_session("c")
    chatbot.get_session("d")

    assert a_id in chatbot.SESSIONS
    assert b_id not in chatbot.SESSIONS


def test_get_session_thread_safe():
    n = 200
    errors = []

    def worker(i):
        try:
            chatbot.get_session(f"thread-{i}")
        except Exception as exc:  # pragma: no cover - chỉ nhằm bắt lỗi bất ngờ
            errors.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
        list(pool.map(worker, range(n)))

    assert not errors
    assert len(chatbot.SESSIONS) == n
