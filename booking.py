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


# LƯU Ý THIẾT KẾ: không còn bảng slot in-memory. Danh sách khung giờ luôn hiển thị
# ĐẦY ĐỦ theo lịch làm việc; việc một khung đã bị đặt hay chưa được kiểm tra TRỰC
# TIẾP VỚI DB ngay tại bước xác nhận (xem book_appointment). Nhờ vậy DB là nguồn
# chân lý duy nhất, không lệch khi chạy nhiều tiến trình / nhiều ngày / sau restart.


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
    """Danh sách ngày làm việc sắp tới (tính trực tiếp từ lịch làm việc hiện tại)."""
    return list(generate_available_slots().keys())


def get_available_times(date_str: str):
    """Khung giờ chuẩn của một ngày — KHÔNG lọc sẵn slot đã đặt.

    Người dùng vẫn thấy/chọn được mọi khung; việc trùng lịch để bước xác nhận đối
    chiếu DB (xem book_appointment). Trả [] nếu không phải ngày làm việc.
    """
    return list(generate_available_slots().get(date_str, []))


def _generate_code():
    return "SHI-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def upcoming_by_phone(phone):
    """Các lịch hẹn 'confirmed' sắp tới (từ hôm nay) của một SĐT, sớm nhất trước."""
    if not phone:
        return []
    from datetime import date
    today = date.today().isoformat()
    out = [a for a in storage.list_appointments()
           if a.get("status") == "confirmed"
           and a.get("patient_phone") == phone
           and a.get("date", "") >= today]
    out.sort(key=lambda a: (a.get("date", ""), a.get("time", "")))
    return out


def cancel_appointment(code):
    """Hủy một lịch hẹn (đặt status='cancelled'). Trả về appt đã hủy, hoặc None.

    Chỉ hủy lịch đang 'confirmed'; sau khi hủy, khung giờ tự trống lại vì
    _confirmed_at chỉ tính lịch 'confirmed'.
    """
    appt = storage.get_appointment(code)
    if not appt or appt.get("status") != "confirmed":
        return None
    storage.set_status(code, "cancelled")
    appt["status"] = "cancelled"
    return appt


def _confirmed_at(date_str, time_str):
    """Lịch hẹn 'confirmed' đang chiếm đúng khung ngày+giờ (nếu có). Đối chiếu DB."""
    for a in storage.list_appointments():
        if (a.get("status") == "confirmed"
                and a.get("date") == date_str
                and a.get("time") == time_str):
            return a
    return None


def book_appointment(session_id, dept_code, doctor_id, date_str, time_str,
                     patient_name="", patient_phone=""):
    """Ghi nhận lịch hẹn. Trả về (ok, payload).

    payload là dict thông tin lịch nếu thành công, hoặc {error: ...} nếu lỗi.
    Khung giờ đã bị chiếm (đối chiếu DB lúc xác nhận):
      - cùng SĐT   -> {duplicate: True, existing: {...}} (chính người này đã đặt).
      - người khác -> {error: ...} (mời chọn giờ khác).
    """
    # Khung giờ phải hợp lệ theo lịch làm việc.
    if time_str not in generate_available_slots().get(date_str, []):
        return False, {"error": "Khung giờ không hợp lệ. Vui lòng chọn giờ khác."}

    doctor_name = get_doctor_name(dept_code, doctor_id)
    if not doctor_name:
        return False, {"error": "Không tìm thấy bác sĩ phù hợp."}

    # NGUỒN CHÂN LÝ = DB: kiểm tra ngay lúc xác nhận xem khung giờ đã bị đặt chưa.
    taken = _confirmed_at(date_str, time_str)
    if taken:
        if patient_phone and taken.get("patient_phone") == patient_phone:
            return False, {"duplicate": True, "existing": taken,
                           "error": "Bạn đã đặt lịch vào khung giờ này rồi."}
        return False, {"error": "Khung giờ này vừa có người đặt. Vui lòng chọn giờ khác."}

    appointment = {
        "code": _generate_code(),
        "session": session_id,
        "patient_name": patient_name or "Khách",
        "patient_phone": patient_phone,
        "department": DEPARTMENTS.get(dept_code, {}).get("name", dept_code),
        "department_code": dept_code,
        "doctor": doctor_name,
        "doctor_id": doctor_id,
        "date": date_str,
        "time": time_str,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "confirmed",
    }

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
