"""
Lớp "TRẢ LỜI LINH HOẠT" — dùng chung cho các bước PICK_*.

Trước đây mỗi bước chỉ chấp nhận đúng `value` của nút; gõ bất cứ thứ gì khác đều
bị lặp lại "bạn chọn ở các nút bên trên". Lớp này cho phép người dùng QUAY LẠI,
ĐỔI BƯỚC, HỎI THÔNG TIN, hoặc KỂ THÊM TRIỆU CHỨNG ngay giữa luồng đặt lịch.

Các hàm ở đây import module bước ngay TRONG THÂN HÀM: `goto_step()` phải gọi
được cả 3 bước, mà cả 3 bước đều gọi ngược lại `flex_intent()` — import ở đầu
file sẽ thành vòng tròn.
"""

from ..core.catalog import DEPARTMENTS
from ..triage import nlu, safety
from .. import triage
from .reply import reply

_PREV_STEP = {           # "quay lại" -> bước trước đó
    "PICK_DOCTOR": "TRIAGE",
    "PICK_DATE": "PICK_DOCTOR",
    "PICK_TIME": "PICK_DATE",
}


def goto_step(sess, state, prefix=""):
    """Đưa hội thoại về đúng một bước, dựng lại câu hỏi + nút của bước đó."""
    from .steps import doctor_step, schedule_step

    if state == "PICK_DOCTOR" and sess.get("dept_code"):
        return doctor_step.start_doctor_pick(sess, prefix=prefix)
    if state == "PICK_DATE" and sess.get("dept_code") and sess.get("doctor_id"):
        return schedule_step.start_date_pick(sess, prefix=prefix)
    if state == "PICK_TIME" and sess.get("date"):
        return schedule_step.start_time_pick(sess, prefix=prefix)
    # Về mô tả triệu chứng: bỏ lựa chọn cũ để triage lại từ đầu.
    sess["dept_code"] = None
    sess["doctor_id"] = None
    return reply(prefix + "Bạn mô tả lại vấn đề răng miệng đang gặp giúp mình nhé.",
                 state="TRIAGE")


def flex_intent(sess, message, current):
    """Ý định "vượt bước" ở PICK_*: quay lại / đổi bước / hỏi thông tin dịch vụ.

    Trả về response nếu bắt được ý định, None nếu để bước hiện tại tự xử lý.
    """
    from .steps import triage_step

    # Phải đứng TRƯỚC wants_change: "còn dịch vụ nào khác không" là câu HỎI danh mục,
    # nếu để wants_change bắt trước thì bị hiểu thành "đổi dịch vụ" -> bắt mô tả lại.
    if nlu.asks_other_service(message):
        return triage_step.service_catalog(sess)

    target = nlu.wants_change(message)
    if target and target != current:
        return goto_step(sess, target, prefix="Được, mình quay lại bước đó. ")

    if nlu.wants_back(message):
        return goto_step(sess, _PREV_STEP.get(current, "TRIAGE"),
                         prefix="Được, mình quay lại bước trước. ")

    # "nội nha là khám gì?" ngay giữa lúc chọn ngày/giờ -> trả lời rồi mời đặt tiếp.
    info_code = triage.info_question_service(message)
    if info_code:
        return triage_step.describe_service(sess, info_code)

    return None


def maybe_new_symptom(sess, message):
    """Người dùng mô tả TRIỆU CHỨNG MỚI giữa lúc đang đặt lịch -> đề nghị đổi dịch vụ.

    Chỉ nhận khi triage đủ tự tin và ra dịch vụ KHÁC dịch vụ đang chọn; nếu không,
    trả None để bước hiện tại hiển thị hướng dẫn của nó.
    """
    results = triage.classify_symptoms(message)
    if not results or triage.confidence_level(results) != "high":
        return None
    top = results[0]
    if top["code"] == sess.get("dept_code"):
        return None

    old = DEPARTMENTS.get(sess.get("dept_code"), {}).get("name", "dịch vụ đang chọn")
    sess["dept_code"] = top["code"]
    sess["doctor_id"] = None
    return reply(
        safety.add_disclaimer(
            f"Theo mô tả mới này, bạn phù hợp với dịch vụ <b>{top['name']}</b> "
            f"<span class='muted'>({top['desc']})</span>.<br>"
            f"Bạn muốn <b>đổi sang</b> dịch vụ này (thay cho {old}) không?"),
        options=[
            {"label": f"✅ Đổi sang: {top['name']}", "value": "yes"},
            {"label": "🔁 Mô tả lại triệu chứng", "value": "no"},
        ],
        state="CONFIRM_DEPT",
    )


def symptom_ack(sess, message):
    """Câu ghi nhận khi người dùng KỂ THÊM TRIỆU CHỨNG giữa lúc đang đặt lịch.

    `maybe_new_symptom()` chỉ trả lời khi cần ĐỔI dịch vụ. Còn hai ca dưới đây nó
    cố ý trả None, và nếu cứ thế rơi xuống câu "Mình chưa rõ..." thì bot hoá ra
    không hiểu gì trong khi người dùng vừa nói đúng chủ đề:

      - triệu chứng mới vẫn thuộc ĐÚNG dịch vụ đang chọn;
      - triage nhận ra vấn đề răng miệng nhưng chưa đủ tự tin để đề nghị đổi.

    Trả về "" nếu câu không dính dáng gì tới triệu chứng (lúc đó câu "chưa rõ" mới
    đúng). Lời gọi triage ở đây dùng chung cache LLM với `maybe_new_symptom()`
    cùng lượt nên không tốn thêm một lượt API.
    """
    dept = DEPARTMENTS.get(sess.get("dept_code"), {}).get("name")
    if not dept:
        return ""

    results = triage.classify_symptoms(message)
    if (results and triage.confidence_level(results) == "high"
            and results[0]["code"] == sess.get("dept_code")):
        return f"Mình ghi nhận thêm mô tả của bạn — vẫn thuộc dịch vụ <b>{dept}</b> nhé. "
    if results or triage.mentions_dental_discomfort(message):
        return (f"Mình ghi nhận mô tả của bạn và vẫn đang giữ dịch vụ <b>{dept}</b> "
                f"— gõ <b>“đổi dịch vụ”</b> nếu bạn muốn chọn dịch vụ khác. ")
    return ""
