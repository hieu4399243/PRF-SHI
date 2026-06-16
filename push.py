"""
Gửi push notification tới điện thoại qua Expo Push Service.

Dùng Expo vì: miễn phí, không cần API key để gửi, chỉ cần "device token"
(dạng ExponentPushToken[...]) mà app native gửi lên khi mở.

Cơ chế:
  - App native (Expo) xin quyền thông báo -> nhận token -> POST lên /api/register-push.
  - Backend lưu token theo session/người dùng (device_tokens.json).
  - Khi đặt lịch / tới hạn nhắc -> backend POST token + nội dung lên Expo,
    Expo đẩy thông báo xuống điện thoại.

Không có token thật (vd. đang test trên máy) -> ghi vào outbox/push_outbox.jsonl
để vẫn kiểm thử được luồng mà không cần điện thoại.
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
TOKENS_PATH = os.path.join(os.path.dirname(__file__), "device_tokens.json")
OUTBOX_DIR = os.path.join(os.path.dirname(__file__), "outbox")
OUTBOX_PATH = os.path.join(OUTBOX_DIR, "push_outbox.jsonl")


# ---------------------------------------------------------------------------
# LƯU / LẤY device token theo session (1 người có thể nhiều thiết bị)
# ---------------------------------------------------------------------------
def _load_tokens():
    if not os.path.exists(TOKENS_PATH):
        return {}
    try:
        with open(TOKENS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_tokens(data):
    with open(TOKENS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def register_token(session_id: str, token: str):
    """App native gọi khi có token. Lưu (không trùng) theo session."""
    if not token:
        return
    data = _load_tokens()
    tokens = set(data.get(session_id, []))
    tokens.add(token)
    data[session_id] = sorted(tokens)
    _save_tokens(data)


def get_tokens(session_id: str):
    return _load_tokens().get(session_id, [])


# ---------------------------------------------------------------------------
# GỬI PUSH
# ---------------------------------------------------------------------------
def _is_real_expo_token(token: str) -> bool:
    return token.startswith("ExponentPushToken[") or token.startswith("ExpoPushToken[")


def _write_outbox(messages):
    os.makedirs(OUTBOX_DIR, exist_ok=True)
    with open(OUTBOX_PATH, "a", encoding="utf-8") as f:
        for m in messages:
            f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), **m},
                               ensure_ascii=False) + "\n")


def send_push(tokens, title: str, body: str, data: dict | None = None):
    """Gửi 1 thông báo tới danh sách token. Trả về dict kết quả.

    Token giả/không hợp lệ -> ghi outbox (demo). Token Expo thật -> gọi HTTP.
    """
    if isinstance(tokens, str):
        tokens = [tokens]
    if not tokens:
        return {"sent": 0, "skipped": 0, "outbox": 0}

    real, demo = [], []
    for t in tokens:
        (real if _is_real_expo_token(t) else demo).append(t)

    # Phần demo (không có điện thoại thật) -> ghi outbox để kiểm thử.
    if demo:
        _write_outbox([{"to": t, "title": title, "body": body, "data": data or {}} for t in demo])

    sent = 0
    if real:
        messages = [{"to": t, "title": title, "body": body, "sound": "default",
                     "data": data or {}} for t in real]
        try:
            req = urllib.request.Request(
                EXPO_PUSH_URL,
                data=json.dumps(messages).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         "Accept": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
                sent = len(real)
        except (urllib.error.URLError, OSError):
            # Lỗi mạng -> không làm gián đoạn nghiệp vụ; ghi outbox để thử lại.
            _write_outbox([{"to": t, "title": title, "body": body,
                            "data": data or {}, "error": "network"} for t in real])

    return {"sent": sent, "outbox": len(demo)}
