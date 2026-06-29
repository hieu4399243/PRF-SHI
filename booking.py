"""
Booking engine — đặt lịch hội thoại giữa bệnh nhân và phòng khám.

Luồng: chọn khoa -> chọn bác sĩ -> chọn ngày -> chọn giờ trống -> xác nhận.
Lịch hẹn được lưu vào appointments.json. Khung giờ đã đặt sẽ bị loại khỏi
danh sách trống để tránh trùng lịch.

(Phần đồng bộ Google Calendar là optional/stretch — xem ghi chú ở cuối file.)
"""

import random
import string
from datetime import datetime

import storage
from data import DOCTORS, DEPARTMENTS, generate_available_slots


def _build_availability():
    """Sinh khung giờ trống, đã LOẠI các slot bị chiếm bởi lịch hẹn hiện có.

    Nhờ vậy slot đã đặt không bị 'mọc lại' sau khi restart (đặc biệt khi dùng DB
    Postgres/Supabase, dữ liệu lịch hẹn còn nguyên qua các lần khởi động).
    """
    slots = generate_available_slots()
    for a in storage.list_appointments():
        if a.get("status") != "confirmed":
            continue
        day = slots.get(a.get("date"))
        if day and a.get("time") in day:
            day.remove(a["time"])
    return slots


# Khung giờ trống (in-memory) — tính 1 lần khi khởi động.
_AVAILABLE = _build_availability()


def get_appointment(code: str):
    """Tra cứu một lịch hẹn theo mã (vd. để sinh file .ics)."""
    return storage.get_appointment(code)


def all_appointments():
    """Toàn bộ lịch hẹn (cho worker nhắc lịch)."""
    return storage.list_appointments()


def mark_reminder_sent(code: str, reminder_key: str):
    """Đánh dấu một loại nhắc đã gửi cho lịch hẹn -> tránh gửi trùng."""
    return storage.set_reminder_sent(code, reminder_key)


def get_doctors(dept_code: str):
    """Danh sách bác sĩ của một khoa."""
    return DOCTORS.get(dept_code, [])


def get_doctor_name(dept_code: str, doctor_id: str):
    for d in get_doctors(dept_code):
        if d["id"] == doctor_id:
            return d["name"]
    return None


def get_available_dates():
    """Danh sách ngày còn ít nhất một khung giờ trống."""
    return [d for d, slots in _AVAILABLE.items() if slots]


def get_available_times(date_str: str):
    """Khung giờ trống của một ngày."""
    return list(_AVAILABLE.get(date_str, []))


def _generate_code():
    return "SHI-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def book_appointment(session_id, dept_code, doctor_id, date_str, time_str, patient_name=""):
    """Ghi nhận lịch hẹn. Trả về (ok, payload).

    payload là dict thông tin lịch nếu thành công, hoặc {error: ...} nếu lỗi.
    """
    # Kiểm tra slot còn trống không (tránh trùng lịch)
    if time_str not in _AVAILABLE.get(date_str, []):
        return False, {"error": "Khung giờ này vừa được đặt hoặc không hợp lệ. Vui lòng chọn giờ khác."}

    doctor_name = get_doctor_name(dept_code, doctor_id)
    if not doctor_name:
        return False, {"error": "Không tìm thấy bác sĩ phù hợp."}

    appointment = {
        "code": _generate_code(),
        "session": session_id,
        "patient_name": patient_name or "Khách",
        "department": DEPARTMENTS.get(dept_code, {}).get("name", dept_code),
        "department_code": dept_code,
        "doctor": doctor_name,
        "doctor_id": doctor_id,
        "date": date_str,
        "time": time_str,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "confirmed",
    }

    # Đánh dấu slot đã đặt -> loại khỏi danh sách trống
    _AVAILABLE[date_str].remove(time_str)

    storage.add_appointment(appointment)

    return True, appointment


# ---------------------------------------------------------------------------
# Google Calendar (optional / stretch)
# ---------------------------------------------------------------------------
def sync_to_google_calendar(appointment):  # pragma: no cover - placeholder
    """Khung đồng bộ Google Calendar.

    Triển khai thật dùng google-api-python-client + OAuth2 để tạo event,
    giúp tránh trùng lịch ở phía bác sĩ. Hiện là no-op để demo chạy độc lập.
    """
    return None
