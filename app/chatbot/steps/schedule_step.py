"""Bước PICK_DATE và PICK_TIME — chọn ngày rồi chọn khung giờ còn trống."""

from ...booking import service as booking
from ...triage import nlu
from .. import flex
from ..reply import format_date, reply
from . import confirm_step


def start_date_pick(sess, prefix=""):
    dates = booking.get_available_dates()
    options = [{"label": format_date(d), "value": d} for d in dates]
    return reply(prefix + "Bạn muốn khám vào ngày nào?", options=options, state="PICK_DATE")


def pick_date(sess, message):
    dates = booking.get_available_dates()

    redirect = flex.flex_intent(sess, message, current="PICK_DATE")
    if redirect:
        return redirect

    chosen = nlu.match_date(message, dates)
    if chosen:
        sess["date"] = chosen
        return start_time_pick(sess)

    switched = flex.maybe_new_symptom(sess, message)
    if switched:
        return switched

    ack = flex.symptom_ack(sess, message)
    return reply(
        (ack + "Bạn muốn khám vào <b>ngày nào</b>?") if ack else
        "Mình chưa nhận ra ngày bạn muốn. Bạn có thể <b>bấm nút</b>, hoặc gõ kiểu "
        "<i>“mai”</i>, <i>“thứ 5”</i>, <i>“20/7”</i>, <i>“sớm nhất”</i> nhé.<br>"
        "<i>Phòng khám chỉ nhận lịch trong các ngày dưới đây.</i>",
        options=[{"label": format_date(d), "value": d} for d in dates],
        state="PICK_DATE",
    )


def start_time_pick(sess, prefix=""):
    times = booking.get_available_times(sess["date"])
    if not times:
        # Ngày đã chọn rơi ra khỏi cửa sổ 5 ngày làm việc (vd. phiên kéo dài
        # qua nửa đêm) -> quay lại chọn ngày, GIỮ nguyên `prefix` (lý do/lỗi)
        # để người dùng không bị đưa về bước chọn ngày mà không hiểu vì sao.
        return start_date_pick(sess, prefix=prefix)
    options = [{"label": t, "value": t} for t in times]
    return reply(
        prefix + f"Các khung giờ trống ngày <b>{format_date(sess['date'])}</b>:",
        options=options,
        state="PICK_TIME",
    )


def pick_time(sess, message):
    times = booking.get_available_times(sess["date"])

    redirect = flex.flex_intent(sess, message, current="PICK_TIME")
    if redirect:
        return redirect

    chosen = nlu.match_time(message, times)
    if chosen:
        sess["time"] = chosen
        # Nếu đã có sẵn tên + SĐT (vd. chọn lại giờ sau khi slot bị chiếm) thì
        # đi thẳng tới bước xác nhận, không hỏi lại tên/số.
        if sess.get("patient_name") and sess.get("patient_phone"):
            return confirm_step.ask_confirm(sess)
        return reply(
            "Cuối cùng, cho mình xin <b>họ tên</b> của bạn để ghi vào lịch hẹn nhé "
            "(bạn có thể gõ tên).",
            state="ASK_NAME",
        )

    # Nói "buổi sáng"/"buổi chiều" mà buổi đó còn nhiều khung -> thu hẹp danh sách
    # thay vì bắt gõ lại từ đầu.
    period = nlu.period_of(message)
    pool = nlu.filter_by_period(times, period)
    if period and pool:
        label = "buổi sáng" if period == "sang" else "buổi chiều"
        return reply(
            f"Các khung giờ <b>{label}</b> ngày {format_date(sess['date'])} — bạn chọn giờ nào?",
            options=[{"label": t, "value": t} for t in pool],
            state="PICK_TIME",
        )

    switched = flex.maybe_new_symptom(sess, message)
    if switched:
        return switched

    ack = flex.symptom_ack(sess, message)
    return reply(
        (ack + "Bạn chọn <b>khung giờ nào</b>?") if ack else
        "Mình chưa nhận ra khung giờ bạn muốn. Bạn có thể <b>bấm nút</b>, hoặc gõ kiểu "
        "<i>“9h”</i>, <i>“14h30”</i>, <i>“buổi sáng”</i>, <i>“sớm nhất”</i> nhé.",
        options=[{"label": t, "value": t} for t in times],
        state="PICK_TIME",
    )
