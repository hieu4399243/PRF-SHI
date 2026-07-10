"""Tests cho cô lập lỗi per-appointment trong reminder_worker.scan_once()."""

from datetime import timedelta

import booking
import push
import reminder_worker


def _valid_appt(code="A001"):
    return {
        "code": code,
        "status": "confirmed",
        "date": "2026-07-10",
        "time": "10:00",
        "department": "Khoa Nội",
        "doctor": "BS. Test",
        "session": "sess-1",
        "reminders_sent": [],
    }


def _broken_appt(code="A002"):
    # thiếu key 'time' -> KeyError khi build appt_dt trong scan_once
    return {
        "code": code,
        "status": "confirmed",
        "date": "2026-07-10",
        "department": "Khoa Nội",
        "doctor": "BS. Test",
        "session": "sess-2",
        "reminders_sent": [],
    }


def test_scan_once_skips_broken_record(monkeypatch):
    appts = [_broken_appt(), _valid_appt()]
    monkeypatch.setattr(booking, "all_appointments", lambda: appts)

    sent_calls = []
    monkeypatch.setattr(push, "send_push", lambda *a, **k: sent_calls.append(a) or {"ok": True})
    monkeypatch.setattr(booking, "mark_reminder_sent", lambda *a, **k: None)

    # không được raise
    n_sent = reminder_worker.scan_once(force=True)

    assert n_sent > 0
    assert len(sent_calls) == len(reminder_worker._rules(_valid_appt()))


def test_scan_once_returns_count_excluding_broken():
    appts = [_broken_appt(), _valid_appt()]
    import unittest.mock as mock

    with mock.patch.object(booking, "all_appointments", return_value=appts), \
         mock.patch.object(push, "send_push", return_value={"ok": True}), \
         mock.patch.object(booking, "mark_reminder_sent", return_value=None):
        n_sent = reminder_worker.scan_once(force=True)

    n_rules = len(reminder_worker._rules(_valid_appt()))
    assert n_sent == n_rules


def test_scan_once_logs_send_error_separately(monkeypatch, capsys):
    appts = [_valid_appt()]
    monkeypatch.setattr(booking, "all_appointments", lambda: appts)
    monkeypatch.setattr(push, "send_push", lambda *a, **k: {"ok": True})

    def _raise_mark(*a, **k):
        raise RuntimeError("db hiccup")

    monkeypatch.setattr(booking, "mark_reminder_sent", _raise_mark)

    n_sent = reminder_worker.scan_once(force=True)

    out = capsys.readouterr().out
    assert n_sent == 0
    assert "[SEND-ERROR]" in out
    assert "[SKIP]" not in out


def test_send_push_reports_failed_count(monkeypatch):
    import urllib.error
    import urllib.request

    def _raise_urlopen(*a, **k):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(urllib.request, "urlopen", _raise_urlopen)

    res = push.send_push(["ExponentPushToken[x]"], "title", "body")

    assert res["failed"] == 1


def test_scan_once_does_not_mark_sent_on_real_push_failure(monkeypatch):
    appts = [_valid_appt()]
    monkeypatch.setattr(booking, "all_appointments", lambda: appts)
    monkeypatch.setattr(push, "send_push",
                         lambda *a, **k: {"sent": 0, "outbox": 0, "failed": 1})

    mark_calls = []
    monkeypatch.setattr(booking, "mark_reminder_sent",
                         lambda *a, **k: mark_calls.append(a))

    reminder_worker.scan_once(force=True)

    assert mark_calls == []


def test_scan_once_marks_sent_when_no_real_token(monkeypatch):
    appts = [_valid_appt()]
    monkeypatch.setattr(booking, "all_appointments", lambda: appts)
    monkeypatch.setattr(push, "send_push",
                         lambda *a, **k: {"sent": 0, "outbox": 1, "failed": 0})

    mark_calls = []
    monkeypatch.setattr(booking, "mark_reminder_sent",
                         lambda *a, **k: mark_calls.append(a))

    reminder_worker.scan_once(force=True)

    assert len(mark_calls) == len(reminder_worker._rules(_valid_appt()))


def test_test_mode_does_not_mark_reminders_sent(monkeypatch):
    appts = [_valid_appt()]
    monkeypatch.setattr(booking, "all_appointments", lambda: appts)
    monkeypatch.setattr(push, "send_push",
                         lambda *a, **k: {"sent": 1, "outbox": 0, "failed": 0})

    mark_calls = []
    monkeypatch.setattr(booking, "mark_reminder_sent",
                         lambda *a, **k: mark_calls.append(a))

    reminder_worker.scan_once(force=True, dry_run=True)

    assert mark_calls == []


def test_now_vn_is_utc_plus_7():
    assert reminder_worker._now_vn().utcoffset() == timedelta(hours=7)


def test_appt_datetime_has_vn_tzinfo():
    appt_dt = reminder_worker._appt_datetime({"date": "2026-08-01", "time": "09:00"})

    assert appt_dt.tzinfo is reminder_worker.VN_TZ
    # so sánh được với _now_vn() mà không raise TypeError (naive/aware mismatch)
    reminder_worker._now_vn() >= appt_dt
