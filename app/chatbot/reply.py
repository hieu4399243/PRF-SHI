"""
Định dạng phản hồi — mọi bước hội thoại đều trả về qua `reply()`.

Giữ nguyên một hình dạng response duy nhất cho cả web demo lẫn app native:

    {"reply": "<html>", "options": [...], "state": "PICK_DATE", "done": False}

`options` là các nút bấm; `state` quyết định lượt sau router gọi bước nào.
"""

import re
from datetime import date

_PHONE_RE = re.compile(r"^0\d{9}$")

_WEEKDAYS = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]


def reply(text, options=None, state=None, done=False, **extra):
    resp = {"reply": text, "options": options or [], "state": state, "done": done}
    resp.update(extra)  # vd. appointment={...} cho app native
    return resp


def normalize_phone(raw: str):
    """Chuẩn hóa & kiểm tra SĐT di động VN. Trả chuỗi 10 số (0xxxxxxxxx) hoặc "" nếu sai.

    Chấp nhận có khoảng trắng/dấu chấm/gạch, và đầu số +84/84 -> quy về 0xxxxxxxxx.
    """
    digits = re.sub(r"[\s.\-()]", "", raw or "")
    if digits.startswith("+84"):
        digits = "0" + digits[3:]
    elif digits.startswith("84") and len(digits) == 11:
        digits = "0" + digits[2:]
    return digits if _PHONE_RE.match(digits) else ""


def format_date(iso: str):
    """YYYY-MM-DD -> 'Thứ X, dd/mm'."""
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{_WEEKDAYS[d.weekday()]}, {d.day:02d}/{d.month:02d}"
