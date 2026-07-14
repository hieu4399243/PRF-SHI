"""
NLU cho các BƯỚC ĐẶT LỊCH — hiểu câu trả lời tự do, không bắt người dùng bấm nút.

Máy trạng thái (chatbot.py) trước đây chỉ chấp nhận đúng `value` của nút:
phải gõ nguyên "bs_sr_01" / "2026-07-15" / "08:30". Người dùng thật sẽ gõ
"bác sĩ Châu", "ai cũng được", "mai", "thứ 5", "9h sáng", "quay lại"...

Module này chuyển những cách nói đó về đúng giá trị mà booking engine hiểu.
Tất cả so khớp đều KHÔNG PHÂN BIỆT DẤU (người Việt hay gõ thiếu dấu).
"""

import re
from datetime import date, timedelta

from .triage import _normalize, _strip_accents


def _na(text: str) -> str:
    """Chuẩn hóa + bỏ dấu, BỎ dấu câu: 'Bác sĩ Châu' -> 'bac si chau'.

    Dùng cho so khớp cụm từ/ý định ("nào cũng được", tên bác sĩ).
    """
    return _strip_accents(_normalize(text or ""))


def _na_punct(text: str) -> str:
    """Bỏ dấu nhưng GIỮ dấu câu: '20/7' -> '20/7', '9:30' -> '9:30'.

    Bắt buộc cho parse ngày/giờ: _normalize() đổi mọi ký tự không phải chữ-số
    thành khoảng trắng, nên '20/7' sẽ thành '20 7' và regex ngày không còn thấy
    dấu '/' để bám vào.
    """
    return " ".join(_strip_accents((text or "").lower()).split())


def _has_any(text_na: str, phrases) -> bool:
    return any(p in text_na for p in phrases)


# ---------------------------------------------------------------------------
# Ý ĐỊNH CHUNG (dùng được ở mọi bước đặt lịch)
# ---------------------------------------------------------------------------
_ANY = ["nao cung duoc", "gi cung duoc", "sao cung duoc", "the nao cung duoc",
        "ai cung duoc", "cung duoc", "tuy ban", "tuy anh", "tuy chi", "tuy nha",
        "tuy y", "ban chon", "ban chon giup", "chon giup toi", "chon ho toi",
        "khong quan trong", "deu duoc", "random", "bat ky", "bat ki"]

_EARLIEST = ["som nhat", "sap nhat", "gan nhat", "cang som cang tot", "dau tien",
             "nhanh nhat", "som"]

_BACK = ["quay lai", "tro lai", "back", "lui lai", "buoc truoc", "quay ve"]


def wants_any(text: str) -> bool:
    """"bác sĩ nào cũng được", "tùy bạn", "sao cũng được"."""
    return _has_any(_na(text), _ANY)


def wants_earliest(text: str) -> bool:
    """"sớm nhất", "càng sớm càng tốt", "gần nhất"."""
    return _has_any(_na(text), _EARLIEST)


def wants_back(text: str) -> bool:
    """"quay lại", "trở lại", "bước trước"."""
    return _has_any(_na(text), _BACK)


# Hỏi về DANH SÁCH bác sĩ chứ không phải chọn: "có bác sĩ khác không?", "còn ai nữa?"
_ASK_OTHER_DOCTOR = [
    "bac si khac", "bac si nao khac", "bac si nao nua", "bac si nao khong",
    "con bac si nao", "con ai khac", "con ai nua", "ai khac khong", "ai nua khong",
    "co ai khac", "nguoi khac", "danh sach bac si", "co nhung bac si nao",
    "bac si nao gioi", "co may bac si", "bao nhieu bac si",
]

# Câu có nhắc tới "bác sĩ" (để phân biệt "gọi tên bác sĩ sai" với gõ linh tinh).
_DOCTOR_WORDS = ["bac si", "bacsi", "bs", "nha si", "nhasi"]


def asks_other_doctor(text: str) -> bool:
    """Người dùng đang HỎI còn bác sĩ nào khác không (không phải đang chọn)."""
    return _has_any(_na(text), _ASK_OTHER_DOCTOR)


# Hỏi về DANH MỤC dịch vụ: "còn dịch vụ nào khác không?", "phòng khám có những gì?"
_ASK_OTHER_SERVICE = [
    "dich vu khac", "dich vu nao khac", "dich vu nao nua", "con dich vu nao",
    "con dich vu gi", "co dich vu nao", "co dich vu gi", "co nhung dich vu nao",
    "nhung dich vu nao", "danh sach dich vu", "cac dich vu", "tat ca dich vu",
    "dich vu gi khac", "co nhung gi", "co gi khac", "khoa nao khac", "muc nao khac",
    "con loai nao", "con gi nua",
]


def asks_other_service(text: str) -> bool:
    """Người dùng HỎI phòng khám còn dịch vụ nào khác (cần liệt kê danh mục)."""
    return _has_any(_na(text), _ASK_OTHER_SERVICE)


def mentions_doctor_word(text: str) -> bool:
    """Câu có nhắc tới "bác sĩ"/"bs" -> nhiều khả năng đang gọi tên một bác sĩ."""
    na = f" {_na(text)} "
    return any(f" {w} " in na for w in _DOCTOR_WORDS)


# ---------------------------------------------------------------------------
# DỪNG ĐẶT LỊCH — "thôi tôi không bị nữa", "hết đau rồi", "không cần đặt nữa".
# Khác với PHỦ ĐỊNH TRIỆU CHỨNG ("tôi không bị đau răng" -> hỏi lại xem bị gì):
# ở đây người dùng muốn KẾT THÚC, nên phải chốt hội thoại chứ không hỏi tiếp.
# Vì vậy các mẫu đều đòi dấu hiệu "thôi / nữa / rồi / không cần".
# ---------------------------------------------------------------------------
_STOP = [
    "khong bi nua", "khong dau nua", "khong con dau", "khong con bi", "khong con nua",
    "het dau roi", "het dau", "do roi", "khoi roi", "khoi benh roi", "tu nhien het",
    "khong can nua", "khong can dat", "khong can kham", "khong muon dat",
    "khong dat nua", "khong kham nua", "khong dat lich nua", "thoi khong dat",
    "thoi khong can", "thoi khoi", "khong muon kham", "de sau", "de hom khac",
]
_STOP_EXACT = {"thoi", "thoi vay", "thoi nhe", "bo qua", "khong dat"}


def wants_stop(text: str) -> bool:
    """Người dùng muốn DỪNG đặt lịch (đã đỡ / đổi ý), không phải mô tả lại."""
    na = _na(text)
    return na in _STOP_EXACT or _has_any(na, _STOP)


def recovered(text: str) -> bool:
    """Dừng vì đã ĐỠ/HẾT triệu chứng -> lời chốt nên chúc mừng thay vì chỉ 'đã hủy'."""
    return _has_any(_na(text), ["het dau", "do roi", "khoi roi", "khong con dau",
                                "khong bi nua", "khong dau nua", "khong con bi",
                                "khoi benh roi", "tu nhien het", "khong con nua"])



_AFFIRM = {"yes", "y", "ok", "oke", "okie", "okay", "co", "co a", "u", "um", "uh",
           "u nhe", "vang", "da", "dung", "dung roi", "dung vay", "chuan",
           "chinh xac", "dong y", "chot", "chot luon", "duoc", "duoc roi", "ro roi",
           "dat lich", "dat di", "muon dat"}
_DENY = {"no", "khong", "khong phai", "khong dung", "sai", "sai roi", "chua dung",
         "khong hop", "chua phai", "khong an"}


def is_affirmative(text: str) -> bool:
    return _na(text) in _AFFIRM


def is_negative(text: str) -> bool:
    return _na(text) in _DENY


# "đổi bác sĩ" / "chọn ngày khác" / "muốn dịch vụ khác" -> nhảy về đúng bước đó.
_CHANGE_VERBS = ["doi", "thay doi", "chon lai", "muon chon", "muon doi", "khac"]
_CHANGE_TARGETS = {
    "PICK_DOCTOR": ["bac si", "bacsi", "bs", "nha si"],
    "PICK_DATE": ["ngay", "hom", "bua"],
    "PICK_TIME": ["gio", "khung gio", "gio giac", "ca"],
    "TRIAGE": ["dich vu", "khoa", "trieu chung"],
}


def wants_change(text: str):
    """Người dùng muốn quay về bước nào? Trả tên state, hoặc None.

    Yêu cầu có CẢ động từ đổi (đổi/chọn lại/khác) VÀ đối tượng (bác sĩ/ngày/giờ/
    dịch vụ) để không cướp lượt của những câu bình thường có chữ "ngày"/"giờ".
    """
    na = _na(text)
    if not _has_any(na, _CHANGE_VERBS):
        return None
    for state, targets in _CHANGE_TARGETS.items():
        if any(f" {t} " in f" {na} " for t in targets):
            return state
    return None


def _index_choice(text: str, n: int):
    """Chọn theo số thứ tự: "1", "chọn 2", "cái thứ 3" -> index 0-based, hoặc None."""
    na = _na(text)
    nums = re.findall(r"\b(\d{1,2})\b", na)
    if len(nums) != 1:  # nhiều số (vd "9h30") -> không phải chọn theo thứ tự
        return None
    i = int(nums[0])
    return i - 1 if 1 <= i <= n else None


# ---------------------------------------------------------------------------
# BÁC SĨ
# ---------------------------------------------------------------------------
_DOCTOR_STOP = {"bs", "bac", "si", "bacsi", "nha", "toi", "muon", "chon", "kham",
                "voi", "gap", "cho", "a", "chi", "anh", "co", "thay", "duoc", "la"}


def match_doctor(text: str, doctors):
    """Tìm bác sĩ theo id / tên đầy đủ / tên riêng ("Châu") / số thứ tự.

    Trả về dict bác sĩ, hoặc None. "ai cũng được" KHÔNG xử lý ở đây (xem wants_any).
    """
    if not doctors:
        return None
    na = _na(text)

    for d in doctors:  # id chính xác (nút bấm)
        if na == _na(d["id"]):
            return d

    for d in doctors:  # tên đầy đủ nằm trong câu
        if _na(d["name"]) in na:
            return d

    # Tên riêng / họ: "bác sĩ châu", "gặp bs an", "châu".
    msg_tokens = {t for t in na.split() if t not in _DOCTOR_STOP and len(t) > 1}
    if msg_tokens:
        hits = []
        for d in doctors:
            name_tokens = {t for t in _na(d["name"]).split() if t not in _DOCTOR_STOP}
            common = msg_tokens & name_tokens
            if common:
                hits.append((len(common), d))
        if hits:
            hits.sort(key=lambda h: h[0], reverse=True)
            # Chỉ nhận khi KHÔNG mơ hồ (vd 2 bác sĩ cùng tên "An" -> hỏi lại).
            if len(hits) == 1 or hits[0][0] > hits[1][0]:
                return hits[0][1]
            return None

    idx = _index_choice(text, len(doctors))
    return doctors[idx] if idx is not None else None


# ---------------------------------------------------------------------------
# NGÀY
# ---------------------------------------------------------------------------
_WEEKDAYS = {  # 0 = Thứ 2 ... 6 = Chủ nhật (khớp date.weekday())
    "thu 2": 0, "thu hai": 0, "t2": 0,
    "thu 3": 1, "thu ba": 1, "t3": 1,
    "thu 4": 2, "thu tu": 2, "t4": 2,
    "thu 5": 3, "thu nam": 3, "t5": 3,
    "thu 6": 4, "thu sau": 4, "t6": 4,
    "thu 7": 5, "thu bay": 5, "t7": 5,
    "chu nhat": 6, "cn": 6,
}


def match_date(text: str, dates):
    """Tìm ngày (ISO 'YYYY-MM-DD') trong danh sách `dates` từ câu nói tự do.

    Hiểu: ISO gốc, "mai"/"ngày mai", "mốt"/"ngày kia", "thứ 5", "20/7", "ngày 20",
    "sớm nhất", số thứ tự. Trả None nếu không chắc.
    """
    if not dates:
        return None
    raw = (text or "").strip()
    if raw in dates:  # value từ nút bấm
        return raw

    na = _na_punct(text)

    if wants_any(text) or wants_earliest(text):
        return dates[0]

    today = date.today()
    if re.search(r"\bngay mai\b|\bmai\b", na):
        target = (today + timedelta(days=1)).isoformat()
        return target if target in dates else None
    if re.search(r"\bngay kia\b|\bmot\b|\bngay mot\b", na):
        target = (today + timedelta(days=2)).isoformat()
        return target if target in dates else None
    if re.search(r"\bhom nay\b|\bnay\b", na):
        target = today.isoformat()
        return target if target in dates else None

    # "thứ 5" -> ngày gần nhất trong danh sách rơi vào thứ đó.
    for label, wd in _WEEKDAYS.items():
        if re.search(rf"\b{re.escape(label)}\b", na):
            for iso in dates:
                if date.fromisoformat(iso).weekday() == wd:
                    return iso
            return None

    # "20/7", "20-7", "20.7", "ngày 20/07"
    m = re.search(r"\b(\d{1,2})\s*[/\-.]\s*(\d{1,2})\b", na)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        for iso in dates:
            d = date.fromisoformat(iso)
            if d.day == day and d.month == month:
                return iso
        return None

    # "ngày 20" (chỉ ngày, không tháng)
    m = re.search(r"\bngay (\d{1,2})\b", na)
    if m:
        day = int(m.group(1))
        for iso in dates:
            if date.fromisoformat(iso).day == day:
                return iso
        return None

    idx = _index_choice(text, len(dates))
    return dates[idx] if idx is not None else None


# ---------------------------------------------------------------------------
# GIỜ
# ---------------------------------------------------------------------------
def period_of(text: str):
    """"sáng" / "chiều" -> lọc khung giờ theo buổi. None nếu không nhắc buổi."""
    na = _na(text)
    if re.search(r"\bsang\b|\bbuoi sang\b", na):
        return "sang"
    if re.search(r"\bchieu\b|\bbuoi chieu\b", na):
        return "chieu"
    return None


def filter_by_period(times, period):
    """Khung giờ thuộc buổi sáng (<12h) hoặc chiều (>=12h)."""
    if not period:
        return list(times)
    out = []
    for t in times:
        hour = int(t.split(":")[0])
        if (period == "sang" and hour < 12) or (period == "chieu" and hour >= 12):
            out.append(t)
    return out


def match_time(text: str, times):
    """Tìm khung giờ trong `times` từ câu nói tự do.

    Hiểu: "08:30" (nút), "9h", "9 giờ", "9h30", "9:30", "14h", "2h chiều",
    "sớm nhất", "sáng"/"chiều" (nếu buổi đó chỉ còn 1 khung), số thứ tự.
    Trả None nếu mơ hồ (vd. "sáng" mà còn nhiều khung) -> để bot hỏi lại.
    """
    if not times:
        return None
    raw = (text or "").strip()
    if raw in times:  # value từ nút bấm
        return raw

    na = _na_punct(text)
    period = period_of(text)

    if wants_any(text) or wants_earliest(text):
        pool = filter_by_period(times, period) or times
        return pool[0]

    # "9h30", "9 gio 30", "9:30", "9h", "14h"  ('gio' phải đứng trước 'g' trong nhánh chọn)
    m = re.search(r"\b(\d{1,2})\s*(?:gio|h|g|:|\.)\s*(\d{2})?\b", na)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        # "2h chiều" -> 14h ; giờ làm việc chiều bắt đầu từ 14h nên 1-6 + "chiều" -> +12
        if period == "chieu" and hour < 12:
            hour += 12
        candidate = f"{hour:02d}:{minute:02d}"
        if candidate in times:
            return candidate
        # Gõ "9h" mà lịch chỉ có "09:00"/"09:30" -> lấy khung đầu tiên của giờ đó.
        same_hour = [t for t in times if t.startswith(f"{hour:02d}:")]
        if same_hour:
            return same_hour[0]
        return None

    # "sáng"/"chiều" đơn thuần: chỉ tự chọn khi buổi đó còn đúng 1 khung.
    if period:
        pool = filter_by_period(times, period)
        return pool[0] if len(pool) == 1 else None

    idx = _index_choice(text, len(times))
    return times[idx] if idx is not None else None
