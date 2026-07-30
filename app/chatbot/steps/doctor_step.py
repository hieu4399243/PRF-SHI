"""
Bước PICK_DOCTOR — chọn bác sĩ cho dịch vụ đã chốt.

Bước này nhận câu trả lời tự do: bấm nút, gõ tên ("bác sĩ Châu"), "ai cũng được",
hỏi "có bác sĩ nào khác không", gọi tên bác sĩ thuộc dịch vụ khác, hoặc... kể
thêm triệu chứng. Thứ tự kiểm tra trong `pick_doctor()` là có chủ đích, đọc
comment tại chỗ trước khi đổi.
"""

from ...booking import service as booking
from ...core.catalog import DEPARTMENTS
from ...triage import nlu
from .. import flex, llm_reply
from ..reply import reply
from . import schedule_step


def start_doctor_pick(sess, prefix=""):
    doctors = booking.get_doctors(sess["dept_code"])
    dept_name = DEPARTMENTS[sess["dept_code"]]["name"]
    options = [{"label": d["name"], "value": d["id"]} for d in doctors]
    if len(doctors) > 1:
        options.append({"label": "🤝 Ai cũng được", "value": "ai cũng được"})
    return reply(
        prefix + f"Tuyệt vời! Bạn muốn đặt lịch với bác sĩ nào cho dịch vụ <b>{dept_name}</b>?",
        options=options,
        state="PICK_DOCTOR",
    )


def pick_doctor(sess, message):
    doctors = booking.get_doctors(sess["dept_code"])

    redirect = flex.flex_intent(sess, message, current="PICK_DOCTOR")
    if redirect:
        return redirect

    # "bác sĩ nào cũng được", "tùy bạn" -> chọn giúp, KHÔNG bắt người dùng chọn lại.
    if doctors and (nlu.wants_any(message) or nlu.wants_earliest(message)):
        chosen = doctors[0]
        sess["doctor_id"] = chosen["id"]
        return schedule_step.start_date_pick(
            sess, prefix=f"Mình xếp bạn với <b>{chosen['name']}</b> nhé. ")

    chosen = nlu.match_doctor(message, doctors)
    if chosen:
        sess["doctor_id"] = chosen["id"]
        return schedule_step.start_date_pick(sess)

    # "có bác sĩ khác không?" -> TRẢ LỜI đúng câu hỏi (kể cả khi chỉ có 1 bác sĩ),
    # thay vì lặp lại hướng dẫn chọn.
    if nlu.asks_other_doctor(message):
        return doctor_roster(sess, doctors)

    # Gọi tên một bác sĩ CÓ THẬT nhưng thuộc dịch vụ khác -> nói rõ, và mời đổi
    # sang dịch vụ mà bác sĩ đó phụ trách.
    other = nlu.match_doctor(message, booking.all_doctors())
    if other and other["dept_code"] != sess["dept_code"]:
        return doctor_other_dept(sess, other)

    switched = flex.maybe_new_symptom(sess, message)
    if switched:
        return switched

    # Có nhắc "bác sĩ ..." nhưng không khớp ai -> báo không tìm thấy, đừng nói chung chung.
    if nlu.mentions_doctor_word(message):
        return doctor_roster(
            sess, doctors,
            prefix="Mình <b>không tìm thấy bác sĩ nào có tên như vậy</b> ở phòng khám. ")

    # Người dùng đang KỂ THÊM TRIỆU CHỨNG chứ không phải chọn bác sĩ -> ghi nhận
    # rồi mời chọn tiếp, đừng nói "chưa rõ bạn muốn khám với bác sĩ nào".
    ack = flex.symptom_ack(sess, message)
    if ack:
        return reply(ack + "Giờ bạn muốn khám với <b>bác sĩ nào</b>?",
                     options=doctor_options(doctors), state="PICK_DOCTOR")

    # Không dính dáng gì tới bác sĩ lẫn triệu chứng -> nhánh "bó tay". Giao cho LLM
    # trả lời, kèm DANH SÁCH BÁC SĨ THẬT để nó không bịa tên (xem llm_reply.py).
    template = (
        "Mình chưa rõ bạn muốn khám với bác sĩ nào. Bạn có thể <b>bấm nút</b>, gõ "
        "<b>tên bác sĩ</b> (vd. <i>“bác sĩ Châu”</i>), gõ <b>“ai cũng được”</b> để mình "
        "xếp giúp, hoặc <b>“đổi dịch vụ”</b> nếu muốn chọn dịch vụ khác.")
    return reply(
        llm_reply.soften(sess, message, "PICK_DOCTOR", template,
                         facts={"BÁC SĨ CỦA DỊCH VỤ NÀY (chỉ được nhắc các tên này)":
                                ", ".join(d["name"] for d in doctors)}),
        options=doctor_options(doctors),
        state="PICK_DOCTOR",
    )


def doctor_options(doctors):
    options = [{"label": d["name"], "value": d["id"]} for d in doctors]
    if len(doctors) > 1:
        options.append({"label": "🤝 Ai cũng được", "value": "ai cũng được"})
    return options


def doctor_roster(sess, doctors, prefix=""):
    """Trả lời câu hỏi "có bác sĩ nào khác không?" — nêu rõ số bác sĩ của dịch vụ này."""
    dept_name = DEPARTMENTS[sess["dept_code"]]["name"]

    if not doctors:  # danh mục thiếu bác sĩ -> không im lặng, mời đổi dịch vụ
        return reply(
            prefix + f"Hiện <b>chưa có bác sĩ nào</b> nhận dịch vụ <b>{dept_name}</b>. "
            "Bạn gõ <b>“đổi dịch vụ”</b> để mình gợi ý dịch vụ khác nhé.",
            state="PICK_DOCTOR",
        )

    if len(doctors) == 1:
        text = (prefix + f"Dịch vụ <b>{dept_name}</b> hiện chỉ có <b>một bác sĩ</b> phụ "
                f"trách: <b>{doctors[0]['name']}</b>.<br>Bạn đặt lịch với bác sĩ này nhé, "
                "hoặc gõ <b>“đổi dịch vụ”</b> nếu muốn khám dịch vụ khác.")
    else:
        names = "<br>".join(f"• <b>{d['name']}</b>" for d in doctors)
        text = (prefix + f"Dịch vụ <b>{dept_name}</b> có <b>{len(doctors)} bác sĩ</b>:<br>"
                f"{names}<br>Bạn muốn khám với ai?")
    return reply(text, options=doctor_options(doctors), state="PICK_DOCTOR")


def doctor_other_dept(sess, doctor):
    """Bác sĩ được gọi tên có thật, nhưng phụ trách dịch vụ KHÁC -> mời đổi dịch vụ."""
    current = DEPARTMENTS[sess["dept_code"]]["name"]
    # CHỜ xác nhận: KHÔNG ghi đè dept_code ngay, nếu không nút "Giữ dịch vụ cũ"
    # sẽ chẳng còn dịch vụ cũ nào để giữ.
    sess["pending_dept_code"] = doctor["dept_code"]
    sess["pending_doctor_id"] = doctor["id"]  # đổi dịch vụ xong thì xếp luôn bác sĩ này
    return reply(
        f"<b>{doctor['name']}</b> phụ trách dịch vụ <b>{doctor['dept_name']}</b>, "
        f"không nhận dịch vụ <b>{current}</b> bạn đang chọn.<br>"
        f"Bạn muốn <b>đổi sang {doctor['dept_name']}</b> để khám với bác sĩ này không?",
        options=[
            {"label": f"✅ Đổi sang: {doctor['dept_name']}", "value": "yes"},
            {"label": f"↩️ Giữ {current}", "value": "no"},
        ],
        state="CONFIRM_DEPT",
    )
