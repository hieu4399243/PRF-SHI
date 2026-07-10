"""
Tests cho M5 (Expo token hết hạn/lỗi ticket).

Bug gốc: `push.send_push()` gọi HTTP tới Expo và chỉ bắt lỗi mạng
(URLError/OSError). Phản hồi HTTP 200 với từng "ticket" báo lỗi (vd
`DeviceNotRegistered`) bị bỏ qua hoàn toàn — token hết hạn không bao giờ bị
xoá khỏi `device_tokens`, và `failed` không phản ánh lỗi cấp ticket (chỉ lỗi
mạng), tồn đọng từ H2.

Residual risk lớn hơn: nếu parse ticket JSON lỗi (body không phải JSON hợp
lệ, hoặc cấu trúc bất ngờ), exception có thể lan lên `send_push()` — hàm này
được `chatbot.py` gọi KHÔNG có try/except bao quanh, SAU KHI lịch hẹn đã lưu
thành công vào storage -> crash `/api/chat` với 500 dù đã đặt lịch xong. Phải
fail-open: lỗi parse ticket không được làm crash send_push hay đổi kết luận
"đã gửi thành công" (HTTP đã 200).
"""

import json
import io
from urllib.error import URLError

import pytest

from app import push
from app import storage


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _expo_body(tickets):
    return json.dumps({"data": tickets}).encode("utf-8")


def test_send_push_removes_token_on_device_not_registered(monkeypatch):
    token = "ExponentPushToken[x]"
    body = _expo_body([{"status": "error",
                        "details": {"error": "DeviceNotRegistered"}}])

    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout=10: _FakeResponse(body))

    removed = []
    monkeypatch.setattr(storage, "remove_token", lambda t: removed.append(t))

    res = push.send_push([token], "Tiêu đề", "Nội dung")

    assert removed == [token]
    assert res["failed"] == 1
    assert res["sent"] == 0


def test_send_push_ok_ticket_does_not_remove_token(monkeypatch):
    token = "ExponentPushToken[x]"
    body = _expo_body([{"status": "ok", "id": "abc"}])

    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout=10: _FakeResponse(body))

    removed = []
    monkeypatch.setattr(storage, "remove_token", lambda t: removed.append(t))

    res = push.send_push([token], "Tiêu đề", "Nội dung")

    assert removed == []
    assert res["failed"] == 0
    assert res["sent"] == 1


def test_send_push_error_ticket_without_device_not_registered_keeps_token(monkeypatch):
    """Ticket báo lỗi nhưng KHÔNG phải DeviceNotRegistered (vd MessageTooBig)
    -> failed tăng nhưng KHÔNG xoá token (token có thể vẫn hợp lệ)."""
    token = "ExponentPushToken[x]"
    body = _expo_body([{"status": "error", "details": {"error": "MessageTooBig"}}])

    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout=10: _FakeResponse(body))

    removed = []
    monkeypatch.setattr(storage, "remove_token", lambda t: removed.append(t))

    res = push.send_push([token], "Tiêu đề", "Nội dung")

    assert removed == []
    assert res["failed"] == 1
    assert res["sent"] == 0


def test_send_push_survives_malformed_ticket_response(monkeypatch):
    """Body không phải JSON hợp lệ -> send_push KHÔNG raise, fail-open (coi
    như đã gửi thành công vì HTTP đã 200)."""
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout=10: _FakeResponse(b"not json"))

    res = push.send_push(["ExponentPushToken[x]"], "Tiêu đề", "Nội dung")

    assert res["sent"] == 1
    assert res["failed"] == 0


def test_send_push_survives_ticket_with_unexpected_shape(monkeypatch):
    """Body là JSON hợp lệ nhưng cấu trúc bất ngờ (vd 'data' không phải list
    của dict) -> vẫn không raise, fail-open."""
    body = json.dumps({"data": ["not-a-dict"]}).encode("utf-8")
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout=10: _FakeResponse(body))

    res = push.send_push(["ExponentPushToken[x]"], "Tiêu đề", "Nội dung")

    assert res["sent"] == 1
    assert res["failed"] == 0


def test_send_push_network_error_still_fails_as_before(monkeypatch):
    """Regression: lỗi mạng (H2) vẫn hoạt động như cũ, không bị M5 phá vỡ."""
    def _raise(*a, **kw):
        raise URLError("boom")

    monkeypatch.setattr("urllib.request.urlopen", _raise)

    res = push.send_push(["ExponentPushToken[x]"], "Tiêu đề", "Nội dung")

    assert res["sent"] == 0
    assert res["failed"] == 1


def test_send_push_remove_token_failure_does_not_affect_result(monkeypatch):
    """Nếu storage.remove_token tự nó lỗi, send_push vẫn phải trả kết quả
    bình thường, không raise."""
    token = "ExponentPushToken[x]"
    body = _expo_body([{"status": "error",
                        "details": {"error": "DeviceNotRegistered"}}])

    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout=10: _FakeResponse(body))
    monkeypatch.setattr(storage, "remove_token",
                        lambda t: (_ for _ in ()).throw(RuntimeError("db down")))

    res = push.send_push([token], "Tiêu đề", "Nội dung")

    assert res["failed"] == 1
