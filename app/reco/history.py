"""
Đọc lịch sử điều trị + dựng bảng đồng xuất hiện — tầng dữ liệu của engine gợi ý.

Module này là ranh giới duy nhất giữa `reco/` và storage: mọi module khác trong
`reco/` chỉ nhận dict/list thuần, nên test được mà không cần DB.

Lọc bắt buộc ở đây: bỏ mọi bản ghi có `service_code` không còn trong danh mục.
Dữ liệu thật còn sót lịch hẹn của phiên bản đa khoa cũ ('ho_hap', 'tieu_hoa'); để
lọt thì engine sẽ gợi ý một dịch vụ mà phòng khám không có.
"""

import threading
import time
from collections import defaultdict

from ..core import storage
from ..core.catalog import DEPARTMENTS

# Số lượt gần nhất đưa vào engine (SEQ 3.3: "20 lịch hẹn gần nhất").
HISTORY_LIMIT = 20

# Số bệnh nhân tối thiểu từng dùng dịch vụ A để tin vào tỉ lệ P(B|A).
# Dưới ngưỡng này, "80% bệnh nhân tương tự" có thể chỉ là 4/5 người -> con số vô
# nghĩa mà lại hiện lên card như một bằng chứng thống kê.
MIN_SUPPORT = 3

# Bảng đồng xuất hiện tính trên TOÀN BỘ bệnh nhân nên không chứa dữ liệu riêng của
# ai, cache chung được. TTL ngắn: dữ liệu mới vào là bảng đổi.
_COOC_TTL_SECONDS = 300
_cooc_cache = {"at": 0.0, "value": None}
_COOC_LOCK = threading.Lock()


def _patient_key(rec):
    """Khoá gộp lịch sử của một người: ưu tiên tài khoản, fallback SĐT."""
    return rec.get("patient_id") or rec.get("patient_phone")


def _valid(rec):
    return rec.get("service_code") in DEPARTMENTS


def recent(patient_id=None, patient_phone=None, limit=HISTORY_LIMIT):
    """`limit` lượt điều trị gần nhất của MỘT bệnh nhân, mới nhất trước.

    Không có định danh nào -> trả rỗng. Đây là chốt chặn quan trọng: tầng dưới
    `storage.list_treatments()` cố tình cho phép gọi không tham số để dựng bảng
    đồng xuất hiện, nên nếu không chặn ở đây thì khách chưa đăng nhập (không có
    id lẫn SĐT) sẽ nhận TOÀN BỘ lịch sử của cả phòng khám làm lịch sử của mình —
    vừa sai (không còn cold-start) vừa là rò rỉ dữ liệu.
    """
    if not patient_id and not patient_phone:
        return []
    rows = storage.list_treatments(patient_id=patient_id,
                                  patient_phone=patient_phone,
                                  limit=None)
    return [r for r in rows if _valid(r)][:limit]


def all_valid():
    """Toàn bộ lịch sử điều trị hợp lệ (dùng cho đồng xuất hiện + độ phổ biến)."""
    return [r for r in storage.list_treatments() if _valid(r)]


def cooccurrence(rows=None, min_support=MIN_SUPPORT):
    """Bảng P(B|A) = tỉ lệ bệnh nhân từng dùng A cũng dùng B.

    Trả về `{a: {b: (conf, n_a)}}`. Đây là collaborative filtering dạng
    market-basket (đồng xuất hiện), KHÔNG phải SVD++ — xem §8.3 doc thiết kế.
    `n_a` được trả kèm để tầng lý do nói được "trên bao nhiêu bệnh nhân".
    """
    rows = all_valid() if rows is None else rows

    services_by_patient = defaultdict(set)
    for rec in rows:
        key = _patient_key(rec)
        if key:  # bản ghi không có cả id lẫn SĐT thì không quy về ai được
            services_by_patient[key].add(rec["service_code"])

    count_a = defaultdict(int)
    count_ab = defaultdict(int)
    for services in services_by_patient.values():
        for a in services:
            count_a[a] += 1
            for b in services:
                if a != b:
                    count_ab[(a, b)] += 1

    table = defaultdict(dict)
    for (a, b), n_ab in count_ab.items():
        n_a = count_a[a]
        if n_a >= min_support:
            table[a][b] = (n_ab / n_a, n_a)
    return dict(table)


def _global_stats():
    """(bảng đồng xuất hiện, độ phổ biến) — tính MỘT LẦT từ MỘT lần đọc, có cache.

    Hai bảng này giống nhau cho mọi bệnh nhân nên cache chung được (không chứa dữ
    liệu riêng của ai). Gộp vào một hàm vì cả hai đều cần toàn bộ lịch sử: tách ra
    thì mỗi request quét bảng hai lần, và `storage` mở một connection Postgres MỚI
    cho mỗi lần đọc -> với Supabase qua mạng, mỗi lượt tốn vài trăm ms.
    """
    now = time.time()
    with _COOC_LOCK:
        if _cooc_cache["value"] is not None and now - _cooc_cache["at"] < _COOC_TTL_SECONDS:
            return _cooc_cache["value"]
    rows = all_valid()
    value = (cooccurrence(rows), popularity(rows))
    with _COOC_LOCK:
        _cooc_cache.update(at=now, value=value)
    return value


def cooccurrence_cached():
    return _global_stats()[0]


def popularity_cached():
    return _global_stats()[1]


def clear_cooccurrence_cache():
    """Xoá cache (dùng trong test, hoặc sau khi seed/backfill dữ liệu)."""
    with _COOC_LOCK:
        _cooc_cache.update(at=0.0, value=None)


def popularity(rows=None):
    """Tỉ trọng mỗi dịch vụ trong toàn bộ lịch sử: `{code: share 0..1}`.

    Đếm theo SỐ BỆNH NHÂN chứ không theo số lượt: một người khám tổng quát 5 lần
    không được làm dịch vụ đó trông phổ biến gấp 5.
    """
    rows = all_valid() if rows is None else rows
    patients_by_service = defaultdict(set)
    for rec in rows:
        key = _patient_key(rec)
        if key:
            patients_by_service[rec["service_code"]].add(key)
    total = len({_patient_key(r) for r in rows if _patient_key(r)})
    if not total:
        return {}
    return {code: len(patients) / total
            for code, patients in patients_by_service.items()}


def upcoming_service_codes(patient_id=None, patient_phone=None, today=None):
    """Các dịch vụ bệnh nhân ĐÃ có lịch hẹn sắp tới -> không gợi ý lại.

    Đọc `appointments` trực tiếp qua storage (không qua `booking/`) để giữ đúng
    quy tắc phụ thuộc: các module nghiệp vụ không import lẫn nhau.
    """
    from datetime import date
    today_iso = (today or date.today()).isoformat()
    codes = set()
    for appt in storage.list_appointments():
        if appt.get("status") != "confirmed":
            continue
        if (appt.get("date") or "") < today_iso:
            continue
        same_person = (
            (patient_phone and appt.get("patient_phone") == patient_phone)
            or (patient_id and appt.get("patient_id") == patient_id)
        )
        if same_person and appt.get("department_code") in DEPARTMENTS:
            codes.add(appt["department_code"])
    return codes
