"""Tests: audit log không được chứa tên bệnh nhân thật khi state là ASK_NAME (H8)."""

import uuid

from app import chatbot
from app import safety


def _new_session_id():
    return f"test-{uuid.uuid4()}"


def test_audit_redacts_message_in_ask_name_state(monkeypatch):
    calls = []
    monkeypatch.setattr(safety, "audit", lambda *args, **kwargs: calls.append(args))

    sid = _new_session_id()
    sess = chatbot.get_session(sid)
    sess["state"] = "ASK_NAME"

    chatbot.handle_message(sid, "Nguyễn Văn A")

    user_calls = [c for c in calls if c[1] == "user"]
    assert user_calls, "expected at least one user audit call"
    first_message = user_calls[0][2]
    assert first_message == "[TÊN ĐÃ ẨN]"
    assert "Nguyễn Văn A" not in first_message


def test_audit_keeps_message_in_other_states(monkeypatch):
    calls = []
    monkeypatch.setattr(safety, "audit", lambda *args, **kwargs: calls.append(args))

    sid = _new_session_id()
    sess = chatbot.get_session(sid)
    sess["state"] = "TRIAGE"

    chatbot.handle_message(sid, "tôi bị đau răng")

    user_calls = [c for c in calls if c[1] == "user"]
    assert user_calls, "expected at least one user audit call"
    first_message = user_calls[0][2]
    assert first_message == "tôi bị đau răng"


def test_patient_name_still_stored_correctly(monkeypatch):
    monkeypatch.setattr(safety, "audit", lambda *args, **kwargs: None)

    sid = _new_session_id()
    sess = chatbot.get_session(sid)
    sess["state"] = "ASK_NAME"

    chatbot.handle_message(sid, "Nguyễn Văn A")

    assert sess["patient_name"] == "Nguyễn Văn A"
