"""
Phiên hội thoại — lưu TRONG BỘ NHỚ tiến trình (dict `SESSIONS`).

Hệ quả phải nhớ: restart server là mất hết phiên, và chạy nhiều worker thì mỗi
worker giữ một bản riêng. Đề tài cố ý chọn "1 process" cho đơn giản; muốn scale
thì thay chỗ này bằng Redis/DB (xem ghi chú `_lock` bên dưới).
"""

import threading
import time
from collections import OrderedDict

SESSIONS = OrderedDict()

MAX_SESSIONS = 2000
SESSION_TTL_SECONDS = 3600  # 1 giờ không hoạt động -> hết hạn

_SESSIONS_LOCK = threading.Lock()


def new_session(reuse_lock=None):
    return {
        "state": "GREET",
        "dept_code": None,
        "doctor_id": None,
        "date": None,
        "time": None,
        "patient_name": "",
        "patient_phone": "",
        "candidates": [],  # các khoa ứng viên từ triage
        # Đề xuất đổi dịch vụ đang CHỜ người dùng xác nhận (vd. gọi tên bác sĩ của
        # dịch vụ khác). Chỉ ghi đè dept_code/doctor_id khi họ bấm đồng ý.
        "pending_dept_code": None,
        "pending_doctor_id": None,
        "cancel_phone": "",  # SĐT dùng khi tra cứu để hủy lịch
        "cancel_code": None,  # mã lịch hẹn đang chờ xác nhận hủy
        "resume_booking": False,  # hủy lịch trùng xong thì đặt tiếp lịch đang dở
        "_last_seen": time.time(),  # không phải dữ liệu nghiệp vụ, chỉ dùng cho eviction
        # _lock KHÔNG serialize được (threading.Lock) — nếu sau này chuyển SESSIONS
        # sang Redis/DB, phải loại bỏ field này khỏi payload lưu trữ, tái tạo Lock khi đọc lại.
        "_lock": reuse_lock or threading.Lock(),
    }


def _evict_if_full_locked():
    """Loại session cũ nhất nếu đã chạm trần. Phải gọi trong lúc giữ _SESSIONS_LOCK."""
    if len(SESSIONS) >= MAX_SESSIONS:
        SESSIONS.popitem(last=False)


def reset_in_place(sess, reuse_lock):
    """Ghi đè nội dung 1 session dict TẠI CHỖ (giữ nguyên object), thay vì tạo
    dict mới rồi thay thế trong SESSIONS.

    Lý do: nếu 1 request khác đang giữ tham chiếu tới dict cũ (đã lấy ra từ
    get_session TRƯỚC KHI session này hết hạn/bị reset) và đang ghi vào nó bên
    trong `with sess["_lock"]:` ở router.py, thay dict bằng object mới sẽ làm
    những thay đổi đó biến mất (không bao giờ được ghi vào bản mà các request
    sau đọc). Reset tại chỗ tránh được lớp bug "mất trạng thái hội thoại" này."""
    fresh = new_session(reuse_lock=reuse_lock)
    sess.clear()
    sess.update(fresh)
    return sess


def get_session(session_id: str):
    with _SESSIONS_LOCK:
        existing = SESSIONS.get(session_id)
        if existing is not None:
            if time.time() - existing["_last_seen"] <= SESSION_TTL_SECONDS:
                existing["_last_seen"] = time.time()
                SESSIONS.move_to_end(session_id)
                return existing
            # Hết hạn -> reset tại chỗ (coi như mới), giữ lại cùng Lock object
            # VÀ cùng dict object — xem reset_in_place().
            reset_in_place(existing, reuse_lock=existing["_lock"])
            SESSIONS.move_to_end(session_id)
            return existing

        _evict_if_full_locked()
        SESSIONS[session_id] = new_session()
        return SESSIONS[session_id]


def reset_session(session_id: str):
    with _SESSIONS_LOCK:
        existing = SESSIONS.get(session_id)
        if existing is not None:
            reset_in_place(existing, reuse_lock=existing["_lock"])
            SESSIONS.move_to_end(session_id)
            return
        _evict_if_full_locked()
        SESSIONS[session_id] = new_session()
