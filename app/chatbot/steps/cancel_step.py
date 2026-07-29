"""
Luồng HỦY LỊCH ĐÃ ĐẶT — CANCEL_ASK_PHONE → CANCEL_PICK → CANCEL_CONFIRM.

Luồng này còn được dùng lại khi đặt trúng lịch TRÙNG: bot mời hủy lịch cũ rồi
đặt tiếp lịch đang dở (cờ `resume_booking` trong phiên).
"""

from ...booking import service as booking
from ...core.text import strip_accents
from ..reply import format_date, normalize_phone, reply
from . import confirm_step

# Nhận diện ý định hủy (khớp cả khi gõ thiếu dấu). Yêu cầu có "lịch/hẹn" để không
# nhầm với nút "hủy" (hủy thao tác) trong lúc đang đặt.
_CANCEL_PATTERNS = ["huy lich", "huy dat lich", "huy lich hen", "huy hen",
                    "huy cuoc hen", "muon huy", "bo lich hen", "xoa lich hen",
                    "cancel lich"]


def is_cancel_request(message: str) -> bool:
    na = strip_accents((message or "").lower())
    return any(p in na for p in _CANCEL_PATTERNS)


def _appt_label(a):
    """Nhãn ngắn gọn cho một lịch hẹn trên nút chọn."""
    return f"{a['department']} • {a['time']} {format_date(a['date'])}"


def start_cancel(sess):
    sess["cancel_phone"] = ""
    sess["cancel_code"] = None
    return reply(
        "Bạn muốn <b>hủy lịch hẹn</b>. Cho mình xin <b>số điện thoại</b> đã dùng khi đặt "
        "để tra cứu nhé (vd. <i>0912345678</i>).",
        state="CANCEL_ASK_PHONE",
    )


def cancel_ask_phone(sess, message):
    phone = normalize_phone(message)
    if not phone:
        return reply(
            "Số điện thoại chưa hợp lệ. Bạn nhập lại số 10 số (vd. <i>0912345678</i>) nhé.",
            state="CANCEL_ASK_PHONE",
        )
    appts = booking.upcoming_by_phone(phone)
    if not appts:
        return reply(
            "Mình không tìm thấy lịch hẹn sắp tới nào với số này. Bạn kiểm tra lại số "
            "điện thoại, hoặc gõ <b>“làm lại”</b> để đặt lịch mới nhé.",
            state="DONE",
        )
    sess["cancel_phone"] = phone
    options = [{"label": _appt_label(a), "value": a["code"]} for a in appts]
    options.append({"label": "↩️ Không hủy nữa", "value": "back"})
    return reply("Bạn muốn hủy lịch hẹn nào dưới đây?", options=options, state="CANCEL_PICK")


def cancel_pick(sess, message):
    low = message.strip().lower()
    if low in {"back", "không", "khong", "thôi", "thoi"}:
        return reply("Đã giữ nguyên lịch hẹn của bạn. Gõ <b>“làm lại”</b> nếu cần đặt lịch mới nhé.",
                     state="DONE")
    appts = booking.upcoming_by_phone(sess.get("cancel_phone", ""))
    chosen = next((a for a in appts if a["code"].lower() == low), None)
    if not chosen:
        return reply("Bạn chọn giúp mình một lịch ở các nút bên trên nhé.", state="CANCEL_PICK")
    sess["cancel_code"] = chosen["code"]
    return reply(
        "Bạn chắc chắn muốn <b>hủy</b> lịch hẹn này?<br>"
        f"• <b>Mã:</b> {chosen['code']}<br>"
        f"• <b>Dịch vụ:</b> {chosen['department']} — {chosen['doctor']}<br>"
        f"• <b>Thời gian:</b> {chosen['time']} ngày {format_date(chosen['date'])}",
        options=[
            {"label": "✅ Hủy lịch này", "value": "confirm"},
            {"label": "↩️ Không hủy", "value": "back"},
        ],
        state="CANCEL_CONFIRM",
    )


def cancel_confirm(sess, message):
    from ...notify import push

    low = message.strip().lower()
    resume = sess.get("resume_booking", False)
    if low in {"back", "không", "khong", "thôi", "thoi", "cancel"}:
        sess["cancel_code"] = None
        sess["resume_booking"] = False
        if resume:
            # Đang đặt lịch mà gặp trùng, chọn GIỮ lịch cũ -> không tạo thêm lịch trùng.
            return reply(
                "Được, mình <b>giữ nguyên lịch cũ</b> và không đặt thêm lịch trùng nhé. "
                "Gõ <b>“làm lại”</b> nếu bạn muốn đặt một lịch khác.",
                state="DONE",
            )
        return reply("Đã giữ nguyên lịch hẹn. Gõ <b>“làm lại”</b> nếu cần nhé.", state="DONE")

    appt = booking.cancel_appointment(sess.get("cancel_code")) if sess.get("cancel_code") else None
    sess["cancel_code"] = None
    if not appt:
        sess["resume_booking"] = False
        return reply(
            "Lịch hẹn này không còn để hủy (có thể đã được hủy trước đó). "
            "Gõ <b>“làm lại”</b> nếu cần nhé.",
            state="DONE",
        )

    if resume:
        # Đã hủy lịch cũ (giải phóng khung giờ) -> đặt tiếp lịch đang dở, không bắt làm lại.
        sess["resume_booking"] = False
        return confirm_step.finalize_booking(sess)

    # Hủy chủ động: báo push + xác nhận đã hủy.
    tokens = push.get_tokens(sess.get("_id", "anon"))
    push.send_push(
        tokens,
        title="🗑️ Đã hủy lịch hẹn",
        body=f"{appt['department']} lúc {appt['time']} ngày {format_date(appt['date'])} đã được hủy.",
        data={"type": "booking_cancelled", "code": appt["code"]},
    )
    return reply(
        "✅ <b>Đã hủy lịch hẹn.</b><br>"
        f"Mã {appt['code']} — {appt['department']} lúc {appt['time']} ngày "
        f"{format_date(appt['date'])} đã được hủy, khung giờ này đã trống trở lại.<br>"
        "<i>Gõ “làm lại” nếu bạn muốn đặt lịch mới.</i>",
        state="DONE",
    )
