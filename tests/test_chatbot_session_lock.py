"""Tests cho khoá per-session bảo vệ field-level write trong handle_message (M10)."""

import threading
import time

import pytest

import chatbot


@pytest.fixture(autouse=True)
def _clean_sessions():
    chatbot.SESSIONS.clear()
    yield
    chatbot.SESSIONS.clear()


def test_new_session_has_lock():
    sess = chatbot._new_session()
    assert isinstance(sess["_lock"], type(threading.Lock()))


def test_reset_session_reuses_same_lock_object():
    sid = "lock-reset"
    sess = chatbot.get_session(sid)
    lock_before = sess["_lock"]

    chatbot.reset_session(sid)
    sess2 = chatbot.get_session(sid)

    assert sess2["_lock"] is lock_before


def test_ttl_expired_session_reuses_same_lock_object(monkeypatch):
    sid = "lock-ttl"
    sess = chatbot.get_session(sid)
    lock_before = sess["_lock"]
    sess["_last_seen"] = time.time() - chatbot._SESSION_TTL_SECONDS - 1

    sess2 = chatbot.get_session(sid)

    assert sess2 is not sess
    assert sess2["_lock"] is lock_before


def test_concurrent_handle_message_same_session_serialized(monkeypatch):
    sid = "lock-concurrent"
    chatbot.get_session(sid)

    original_reply = chatbot._reply

    def slow_reply(*args, **kwargs):
        time.sleep(0.01)
        return original_reply(*args, **kwargs)

    monkeypatch.setattr(chatbot, "_reply", slow_reply)

    errors = []

    def worker():
        try:
            chatbot.handle_message(sid, "làm lại")
        except Exception as exc:  # pragma: no cover - fail loudly via list
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not errors
    assert chatbot.SESSIONS[sid]["state"] == "TRIAGE"


def test_different_sessions_not_blocked_by_each_other():
    sid_a, sid_b = "lock-a", "lock-b"
    chatbot.get_session(sid_a)
    chatbot.get_session(sid_b)

    results = {}

    def worker(sid, key):
        results[key] = chatbot.handle_message(sid, "làm lại")

    t1 = threading.Thread(target=worker, args=(sid_a, "a"))
    t2 = threading.Thread(target=worker, args=(sid_b, "b"))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert not t1.is_alive()
    assert not t2.is_alive()
    assert results["a"]["state"] == "TRIAGE"
    assert results["b"]["state"] == "TRIAGE"
