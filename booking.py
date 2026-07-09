"""
Booking engine — đặt lịch hội thoại giữa bệnh nhân và phòng khám.

Luồng: chọn khoa -> chọn bác sĩ -> chọn ngày -> chọn giờ trống -> xác nhận.
Lịch hẹn được lưu vào appointments.json. Khung giờ đã đặt sẽ bị loại khỏi
danh sách trống để tránh trùng lịch.

(Phần đồng bộ Google Calendar là optional/stretch — xem ghi chú ở cuối file.)
"""

import secrets
import string
from datetime import datetime

import storage
from data import DOCTORS, DEPARTMENTS, WORK_SLOTS, generate_available_slots


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
    alphabet = string.ascii_uppercase + string.digits
    return "SHI-" + "".join(secrets.choice(alphabet) for _ in range(6))


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

    return _insert_with_race_guard(appointment, date_str, time_str, patient_phone,
                                    retry=True)


def _insert_with_race_guard(appointment, date_str, time_str, patient_phone,
                            retry):
    """Gọi storage.add_appointment, bắt UniqueViolation do race giữa 2 request
    đặt cùng khung giờ gần như đồng thời (xem UNIQUE INDEX ux_appointments_slot
    trong storage.py).

    `UniqueViolation` có thể đến từ 2 nguồn khác nhau vì `appointments.code` là
    PRIMARY KEY từ trước khi có `ux_appointments_slot`:
      - constraint ux_appointments_slot -> đúng ý: khung giờ vừa bị bên khác
        chiếm trong lúc race. Trả lỗi giống nhánh "đã có người đặt" ở trên.
      - constraint khác (vd appointments_pkey, do _generate_code() hiếm khi
        sinh trùng mã) -> khung giờ KHÔNG thực sự bị chiếm, KHÔNG được gọi
        _confirmed_at (sẽ trả None -> AttributeError khi code cũ giả định
        taken luôn có giá trị). Sinh mã mới và retry insert một lần; nếu vẫn
        lỗi, trả lỗi hệ thống chung thay vì để exception rò rỉ ra route Flask.
    """
    try:
        storage.add_appointment(appointment)
    except Exception as exc:
        try:
            import psycopg
        except ImportError:
            raise exc
        if not isinstance(exc, psycopg.errors.UniqueViolation):
            raise
        constraint_name = getattr(getattr(exc, "diag", None),
                                  "constraint_name", None)
        if constraint_name == "ux_appointments_slot":
            taken = _confirmed_at(date_str, time_str)
            if patient_phone and taken and taken.get("patient_phone") == patient_phone:
                return False, {"duplicate": True, "existing": taken,
                               "error": "Bạn đã đặt lịch vào khung giờ này rồi."}
            return False, {"error": "Khung giờ này vừa có người đặt. "
                                    "Vui lòng chọn giờ khác."}
        # Không phải lỗi trùng slot (vd trùng code ngẫu nhiên) -> không đụng
        # taken/_confirmed_at, chỉ retry với code mới.
        if not retry:
            return False, {"error": "Lỗi hệ thống, vui lòng thử lại."}
        appointment = dict(appointment, code=_generate_code())
        return _insert_with_race_guard(appointment, date_str, time_str,
                                       patient_phone, retry=False)

    return True, appointment


# ---------------------------------------------------------------------------
# TRA CỨU CHO ADMIN / BÁC SĨ (read-only trên DB, không đổi nghiệp vụ đặt lịch)
# Bệnh nhân dùng chatbot để ĐẶT lịch; admin/bác sĩ dùng các hàm dưới để XEM lại
# lịch đã đặt và lịch làm việc. Tất cả đọc qua storage nên đúng cả JSON lẫn Postgres.
# ---------------------------------------------------------------------------
def all_doctors():
    """Danh sách phẳng mọi bác sĩ kèm dịch vụ phụ trách (cho bộ lọc ở trang admin)."""
    out = []
    for dept_code, docs in DOCTORS.items():
        for d in docs:
            out.append({
                "id": d["id"],
                "name": d["name"],
                "dept_code": dept_code,
                "dept_name": DEPARTMENTS.get(dept_code, {}).get("name", dept_code),
            })
    return out


def query_appointments(date=None, doctor_id=None, dept_code=None,
                       phone=None, status=None):
    """Lọc lịch hẹn theo nhiều tiêu chí, sắp theo ngày rồi giờ.

    Tiêu chí nào để None thì bỏ qua. Dùng cho màn hình quản trị: xem lịch theo
    ngày, theo bác sĩ, theo trạng thái (confirmed/cancelled) hoặc theo SĐT bệnh nhân.
    """
    out = storage.list_appointments()
    if status:
        out = [a for a in out if a.get("status") == status]
    if date:
        out = [a for a in out if a.get("date") == date]
    if doctor_id:
        out = [a for a in out if a.get("doctor_id") == doctor_id]
    if dept_code:
        out = [a for a in out if a.get("department_code") == dept_code]
    if phone:
        out = [a for a in out if a.get("patient_phone") == phone]
    out.sort(key=lambda a: (a.get("date", ""), a.get("time", "")))
    return out


def doctor_day_schedule(doctor_id, date_str):
    """Lịch làm việc của MỘT bác sĩ trong MỘT ngày.

    Trả về danh sách theo từng khung giờ chuẩn: {time, appt} — appt là lịch hẹn
    'confirmed' đang chiếm khung đó (nếu có), None nếu còn trống. Nhờ đó bác sĩ
    thấy ngay mình bận/rảnh khung nào, ai đặt.

    Ngày trong cửa sổ làm việc sắp tới dùng khung giờ trống thực tế; ngày ngoài
    cửa sổ (vd. lịch quá khứ để tra cứu) fallback về khung giờ chuẩn `WORK_SLOTS`
    để vẫn hiển thị được lưới bận/trống.
    """
    slots = generate_available_slots().get(date_str) or list(WORK_SLOTS)
    booked = {a["time"]: a for a in query_appointments(
        date=date_str, doctor_id=doctor_id, status="confirmed")}
    return [{"time": s, "appt": booked.get(s)} for s in slots]


def known_dates():
    """Các ngày admin có thể lọc/xem: gộp ngày làm việc sắp tới + ngày ĐÃ có lịch.

    Nhờ vậy dropdown ngày ở trang quản trị hiển thị được cả lịch quá khứ (không chỉ
    5 ngày làm việc sắp tới), tránh cảm giác 'lọc theo ngày không ra gì'.
    """
    working = set(get_available_dates())
    booked = {a.get("date") for a in storage.list_appointments() if a.get("date")}
    return sorted(working | booked, reverse=True)


def admin_summary():
    """Thống kê nhanh cho trang quản trị: tổng số lịch theo trạng thái + theo dịch vụ."""
    appts = storage.list_appointments()
    by_status, by_dept = {}, {}
    for a in appts:
        st = a.get("status", "?")
        by_status[st] = by_status.get(st, 0) + 1
        if st == "confirmed":
            dn = a.get("department", a.get("department_code", "?"))
            by_dept[dn] = by_dept.get(dn, 0) + 1
    return {
        "total": len(appts),
        "confirmed": by_status.get("confirmed", 0),
        "cancelled": by_status.get("cancelled", 0),
        "by_status": by_status,
        "by_department": by_dept,
    }


# ---------------------------------------------------------------------------
# Google Calendar (optional / stretch)
# ---------------------------------------------------------------------------
def sync_to_google_calendar(appointment):  # pragma: no cover - placeholder
    """Khung đồng bộ Google Calendar.

    Triển khai thật dùng google-api-python-client + OAuth2 để tạo event,
    giúp tránh trùng lịch ở phía bác sĩ. Hiện là no-op để demo chạy độc lập.
    """
    return None
