"""
Bước ASK_NAME → ASK_PHONE → CONFIRM_BOOKING — thu thập thông tin và chốt lịch.

`finalize_booking()` là nơi duy nhất thực sự ghi lịch hẹn, và được dùng lại ở
luồng hủy (hủy lịch trùng xong thì đặt tiếp lịch đang dở).
"""

from ...booking import calendar_ics
from ...booking import service as booking
from ...core.catalog import DEPARTMENTS
from ...notify import push
from ..reply import format_date, normalize_phone, reply


def ask_name(sess, message):
    sess["patient_name"] = message[:60] if message else "Khách"
    return reply(
        "Cảm ơn bạn. Cho mình xin thêm <b>số điện thoại</b> để xác nhận và nhắc lịch nhé "
        "(vd. <i>0912 345 678</i>).",
        state="ASK_PHONE",
    )


def ask_phone(sess, message):
    phone = normalize_phone(message)
    if not phone:
        return reply(
            "Số điện thoại chưa hợp lệ. Bạn nhập giúp mình số di động Việt Nam "
            "gồm <b>10 số</b> (bắt đầu bằng 0, vd. <i>0912345678</i>) nhé.",
            state="ASK_PHONE",
        )
    sess["patient_phone"] = phone
    return ask_confirm(sess)


def ask_confirm(sess):
    """Hiển thị bản tóm tắt lịch hẹn kèm nút xác nhận / hủy."""
    return reply(
        booking_summary(sess),
        options=[
            {"label": "✅ Xác nhận đặt lịch", "value": "confirm"},
            {"label": "❌ Hủy", "value": "cancel"},
        ],
        state="CONFIRM_BOOKING",
    )


def booking_summary(sess):
    dept_name = DEPARTMENTS[sess["dept_code"]]["name"]
    doctor_name = booking.get_doctor_name(sess["dept_code"], sess["doctor_id"])
    return (
        "Vui lòng xác nhận lịch hẹn:<br>"
        f"• <b>Bệnh nhân:</b> {sess['patient_name']}<br>"
        f"• <b>Điện thoại:</b> {sess['patient_phone']}<br>"
        f"• <b>Dịch vụ:</b> {dept_name}<br>"
        f"• <b>Bác sĩ:</b> {doctor_name}<br>"
        f"• <b>Thời gian:</b> {sess['time']} ngày {format_date(sess['date'])}"
    )


def confirm_booking(sess, message):
    low = message.lower()
    if low in {"cancel", "hủy", "huỷ", "không"}:
        return reply("Đã hủy thao tác đặt lịch. Gõ <b>“làm lại”</b> nếu bạn muốn bắt đầu lại nhé.",
                     state="DONE")
    return finalize_booking(sess)


def finalize_booking(sess):
    """Ghi nhận lịch từ dữ liệu trong phiên. Dùng lại được sau khi hủy lịch trùng."""
    # Import trễ: schedule_step đã import module này ở đầu file (bước chọn giờ dẫn
    # tới bước xác nhận), nên import ngược ở đầu file sẽ thành vòng tròn.
    from . import schedule_step

    ok, payload = booking.book_appointment(
        session_id=sess.get("_id", "anon"),
        dept_code=sess["dept_code"],
        doctor_id=sess["doctor_id"],
        date_str=sess["date"],
        time_str=sess["time"],
        patient_name=sess["patient_name"],
        patient_phone=sess["patient_phone"],
        # Ai ĐANG ĐĂNG NHẬP, không phải ai được gõ vào ô SĐT. main.chat() đóng dấu
        # vào phiên từ JWT — xem `_user_id` ở app/chatbot/session.py.
        booked_by_user_id=sess.get("_user_id"),
    )
    if not ok:
        if payload.get("duplicate"):
            dup = payload["existing"]
            sess["cancel_code"] = dup["code"]
            sess["resume_booking"] = True
            return reply(
                "⚠️ <b>Bạn đã đặt lịch vào đúng khung giờ này rồi.</b><br>"
                f"• <b>Mã lịch hẹn:</b> {dup['code']}<br>"
                f"• <b>Dịch vụ:</b> {dup['department']} — {dup['doctor']}<br>"
                f"• <b>Thời gian:</b> {dup['time']} ngày {format_date(dup['date'])}<br><br>"
                "Bạn có muốn <b>hủy lịch đặt trước đó</b> và đặt lại không?",
                options=[
                    {"label": "🗑️ Hủy lịch cũ & đặt lại", "value": "confirm"},
                    {"label": "↩️ Giữ lịch cũ", "value": "back"},
                ],
                state="CANCEL_CONFIRM",
            )
        # slot vừa bị đặt mất -> quay lại chọn giờ (hiển thị lại các khung giờ còn trống)
        return schedule_step.start_time_pick(
            sess, prefix=payload["error"] + " Mời bạn chọn lại khung giờ.<br><br>")

    # Bắn push xác nhận tới điện thoại của bệnh nhân (nếu app đã đăng ký token).
    tokens = push.get_tokens(sess.get("_id", "anon"))
    push.send_push(
        tokens,
        title="✅ Đặt lịch thành công",
        body=f"{payload['department']} - {payload['doctor']} lúc "
             f"{payload['time']} ngày {format_date(payload['date'])}. Mã: {payload['code']}",
        data={"type": "booking_confirmed", "code": payload["code"]},
    )

    gcal = calendar_ics.google_calendar_link(payload)
    ics_url = f"/api/ics/{payload['code']}"
    return reply(
        "🎉 <b>Đặt lịch thành công!</b><br>"
        f"• <b>Mã lịch hẹn:</b> {payload['code']}<br>"
        f"• <b>Dịch vụ:</b> {payload['department']} — {payload['doctor']}<br>"
        f"• <b>Thời gian:</b> {payload['time']} ngày {format_date(payload['date'])}<br><br>"
        "📅 <b>Thêm vào lịch của bạn để được nhắc tự động</b> (trước 1 ngày &amp; 1 giờ):<br>"
        f"<a class='cal-link' href='{ics_url}'>⬇️ Thêm vào Lịch (iPhone/Outlook/.ics)</a><br>"
        f"<a class='cal-link' href='{gcal}' target='_blank' rel='noopener'>📆 Thêm vào Google Calendar</a>"
        "<br><br>Chúc bạn mau khỏe! 💚<br>"
        "<i>Gõ “làm lại” nếu muốn đặt thêm lịch.</i>",
        state="DONE",
        done=True,
        # Dữ liệu có cấu trúc để app native hẹn local notification + thêm lịch.
        appointment={
            "code": payload["code"],
            "department": payload["department"],
            "doctor": payload["doctor"],
            "date": payload["date"],
            "time": payload["time"],
            "gcalUrl": gcal,
        },
    )
