"""
Sinh file lịch chuẩn iCalendar (.ics) cho một lịch hẹn.

File .ics thêm được vào MỌI ứng dụng lịch (Google Calendar, Lịch iPhone/Mac,
Outlook...) và kèm sẵn lời nhắc (VALARM) -> app lịch của bệnh nhân sẽ tự
thông báo trước giờ khám. Không cần OAuth / API key.
"""

from datetime import datetime, timedelta

APPT_DURATION_MIN = 30  # mỗi lượt khám 30 phút


def _fmt(dt: datetime) -> str:
    """datetime -> 'YYYYMMDDTHHMMSS' (giờ địa phương, dùng kèm TZID)."""
    return dt.strftime("%Y%m%dT%H%M%S")


def _esc(value) -> str:
    """Escape 1 giá trị theo RFC 5545 §3.3.11 trước khi nội suy vào nội dung .ics."""
    s = str(value)
    s = s.replace("\\", "\\\\")  # backslash TRƯỚC TIÊN
    s = s.replace(";", "\\;")
    s = s.replace(",", "\\,")
    s = s.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return s


def build_ics(appointment: dict) -> str:
    """Tạo nội dung file .ics từ một lịch hẹn (dict trả về bởi booking)."""
    start = datetime.fromisoformat(f"{appointment['date']}T{appointment['time']}:00")
    end = start + timedelta(minutes=APPT_DURATION_MIN)
    now = datetime.now()

    summary = f"Nha khoa SHI: {_esc(appointment['department'])} - {_esc(appointment['doctor'])}"
    description = (
        f"Lịch hẹn tại Nha khoa SHI.\\n"
        f"Mã lịch hẹn: {_esc(appointment['code'])}\\n"
        f"Bệnh nhân: {_esc(appointment.get('patient_name', 'Khách'))}\\n"
        f"Dịch vụ: {_esc(appointment['department'])}\\n"
        f"Bác sĩ: {_esc(appointment['doctor'])}\\n"
        f"Lưu ý: vui lòng đến trước giờ hẹn 15 phút."
    )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SHI//Nha khoa SHI//VI",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        # Khai báo múi giờ Việt Nam (+07, không có giờ mùa hè)
        "BEGIN:VTIMEZONE",
        "TZID:Asia/Ho_Chi_Minh",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:+0700",
        "TZOFFSETTO:+0700",
        "TZNAME:+07",
        "DTSTART:19700101T000000",
        "END:STANDARD",
        "END:VTIMEZONE",
        "BEGIN:VEVENT",
        f"UID:{appointment['code']}@shi-health",
        f"DTSTAMP:{_fmt(now)}",
        f"DTSTART;TZID=Asia/Ho_Chi_Minh:{_fmt(start)}",
        f"DTEND;TZID=Asia/Ho_Chi_Minh:{_fmt(end)}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        "LOCATION:Nha khoa SHI",
        "STATUS:CONFIRMED",
        # Nhắc trước 1 ngày
        "BEGIN:VALARM",
        "TRIGGER:-P1D",
        "ACTION:DISPLAY",
        "DESCRIPTION:Nhắc lịch khám tại SHI (còn 1 ngày)",
        "END:VALARM",
        # Nhắc trước 1 giờ
        "BEGIN:VALARM",
        "TRIGGER:-PT1H",
        "ACTION:DISPLAY",
        "DESCRIPTION:Nhắc lịch khám tại SHI (còn 1 giờ)",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


def google_calendar_link(appointment: dict) -> str:
    """Link 'thêm nhanh vào Google Calendar' (mở web, không cần file).

    Hữu ích cho người dùng Google Calendar: bấm là mở sẵn form tạo sự kiện.
    """
    from urllib.parse import urlencode

    start = datetime.fromisoformat(f"{appointment['date']}T{appointment['time']}:00")
    end = start + timedelta(minutes=APPT_DURATION_MIN)
    # Google nhận giờ UTC -> trừ 7 tiếng từ giờ VN.
    start_utc = start - timedelta(hours=7)
    end_utc = end - timedelta(hours=7)

    params = {
        "action": "TEMPLATE",
        "text": f"Nha khoa SHI: {appointment['department']} - {appointment['doctor']}",
        "dates": f"{_fmt(start_utc)}Z/{_fmt(end_utc)}Z",
        "details": f"Mã lịch hẹn: {appointment['code']} - Nha khoa SHI",
        "location": "Nha khoa SHI",
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params)
