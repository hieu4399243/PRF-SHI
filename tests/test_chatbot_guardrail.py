"""Tests cho guardrail chặn yêu cầu chẩn đoán ở MỌI state khác TRIAGE (M1)."""

import pytest

from app import chatbot


@pytest.fixture(autouse=True)
def _clean_sessions():
    chatbot.SESSIONS.clear()
    yield
    chatbot.SESSIONS.clear()


def test_diagnosis_request_blocked_outside_triage():
    sid = "guard-1"
    sess = chatbot.get_session(sid)
    sess["state"] = "PICK_TIME"

    resp = chatbot.handle_message(sid, "bác sĩ ơi tôi bị bệnh gì")

    assert "không thể chẩn đoán" in resp["reply"]
    assert resp["state"] == "PICK_TIME"
    assert chatbot.SESSIONS[sid]["state"] == "PICK_TIME"


def test_diagnosis_request_in_triage_unchanged():
    sid = "guard-2"
    sess = chatbot.get_session(sid)
    sess["state"] = "TRIAGE"

    resp = chatbot.handle_message(sid, "tôi bị bệnh gì, răng tôi đau nhức dữ dội")

    # Hành vi cũ: diag_note lồng trong response triage, KHÔNG phải disclaimer
    # độc lập của guardrail mới (guardrail bị loại trừ ở state TRIAGE).
    assert "không thể chẩn đoán bệnh hay kê đơn" in resp["reply"]
    assert "bạn chọn đúng dịch vụ nha khoa và đặt lịch khám" not in resp["reply"]


def test_diagnosis_guardrail_does_not_override_cancel_intent():
    sid = "guard-3"
    sess = chatbot.get_session(sid)
    sess["state"] = "DONE"

    resp = chatbot.handle_message(
        sid, "huỷ lịch giúp tôi, tôi phải uống thuốc gì trước khi khám không"
    )

    assert resp["state"] == "CANCEL_ASK_PHONE"
    assert "không thể chẩn đoán" not in resp["reply"]


def test_diagnosis_guardrail_does_not_override_info_question():
    sid = "guard-4"
    sess = chatbot.get_session(sid)
    sess["state"] = "DONE"

    resp = chatbot.handle_message(
        sid, "Khám tổng quát là gì, tôi phải uống thuốc gì trước khi khám vậy?"
    )

    assert resp["state"] == "CONFIRM_DEPT"
    assert "không thể chẩn đoán" not in resp["reply"]
