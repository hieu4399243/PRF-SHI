"""
Bước TRIAGE + CONFIRM_DEPT — từ mô tả triệu chứng tới chốt một nhóm dịch vụ.

Đây là cửa ngõ của hội thoại: `do_triage()` gọi bộ phân loại (rule-based hoặc
LLM, xem app/triage/), rồi tuỳ ĐỘ TIN CẬY mà chốt luôn, đưa 2-3 lựa chọn, hay
hỏi thêm.
"""

from ...core.catalog import DEPARTMENTS, SERVICE_INFO
from ...triage import nlu, safety
from ... import triage
from ..reply import reply


def do_triage(sess, message):
    # Người dùng yêu cầu chẩn đoán/kê đơn -> chặn nhưng vẫn cố định hướng khoa.
    diag_note = ""
    if safety.is_diagnosis_request(message):
        diag_note = ("Mình <b>không thể chẩn đoán bệnh hay kê đơn</b>, nhưng có thể "
                     "giúp bạn chọn đúng dịch vụ nha khoa. ")

    results = triage.classify_symptoms(message)
    conf = triage.confidence_level(results)

    if conf == "low":
        # Người dùng PHỦ ĐỊNH triệu chứng ("tôi không bị đau răng") -> không được
        # gợi ý đúng cái dịch vụ họ vừa loại trừ; ghi nhận rồi hỏi lại cho đúng ý.
        negated = triage.negated_matches(message)
        if negated:
            return reply(
                diag_note + "Mình ghi nhận bạn <b>không</b> gặp vấn đề đó. "
                "Vậy hiện tại bạn đang khó chịu ở đâu, cảm giác thế nào? "
                "<i>(hoặc bạn chỉ muốn đi khám kiểm tra định kỳ?)</i>",
                options=[
                    {"label": "🦷 Khám tổng quát / cạo vôi", "value": "kham_tong_quat"},
                    {"label": "🔁 Mô tả triệu chứng khác", "value": "redo"},
                ],
                state="CONFIRM_DEPT",
            )
        # Không trúng từ khóa dịch vụ cụ thể, NHƯNG câu vẫn cho thấy vấn đề răng
        # miệng (bộ phận + cảm giác khó chịu) -> đưa lựa chọn có cấu trúc để chốt.
        if triage.mentions_dental_discomfort(message):
            return dental_followup(diag_note)
        # Không nhận ra gì -> hỏi follow-up có cấu trúc.
        return reply(
            diag_note + "Mình chưa rõ triệu chứng của bạn. "
            + triage.FOLLOWUP_QUESTIONS[0]
            + "<br><i>Bạn có thể mô tả cụ thể hơn, ví dụ vị trí đau, thời gian, mức độ.</i>",
            state="TRIAGE",
        )

    sess["candidates"] = results
    top = results[0]

    if conf == "high":
        sess["dept_code"] = top["code"]
        text = (diag_note + f"Dựa trên mô tả, bạn nên dùng dịch vụ <b>{top['name']}</b> "
                f"<span class='muted'>({top['desc']})</span>.<br>Bạn có muốn đặt lịch dịch vụ này không?")
        return reply(
            safety.add_disclaimer(text),
            options=[
                {"label": f"✅ Đặt lịch: {top['name']}", "value": "yes"},
                {"label": "🔁 Mô tả lại triệu chứng", "value": "no"},
            ],
            state="CONFIRM_DEPT",
        )

    # medium -> đưa ra 2-3 dịch vụ ứng viên để người dùng chọn.
    options = [{"label": r["name"], "value": r["code"]} for r in results[:3]]
    options.append({"label": "🔁 Mô tả lại", "value": "redo"})
    return reply(
        diag_note + "Vấn đề của bạn có thể liên quan vài dịch vụ. "
        "Bạn muốn dùng dịch vụ nào dưới đây?",
        options=options,
        state="CONFIRM_DEPT",
    )


def dental_followup(diag_note=""):
    """Câu mơ hồ nhưng rõ là vấn đề răng miệng -> cho chọn mô tả gần nhất.

    Mỗi lựa chọn ánh xạ thẳng sang một mã dịch vụ; confirm_dept xử lý tiếp.
    """
    return reply(
        diag_note + "Mình hiểu bạn đang khó chịu ở răng miệng. Để hỗ trợ đúng, "
        "bạn chọn mô tả <b>gần nhất</b> nhé:",
        options=[
            {"label": "Ê buốt / đau khi ăn nóng–lạnh–ngọt", "value": "sau_rang"},
            {"label": "Đau nhức dữ dội / theo nhịp / về đêm", "value": "noi_nha"},
            {"label": "Chảy máu / sưng nướu, hôi miệng", "value": "nha_chu"},
            {"label": "Chỉ khó chịu nhẹ — muốn khám tổng quát", "value": "kham_tong_quat"},
            {"label": "🔁 Mô tả lại triệu chứng", "value": "redo"},
        ],
        state="CONFIRM_DEPT",
    )


def describe_service(sess, code, diag_note=""):
    """Trả lời câu hỏi 'X là khám gì / là gì' bằng mô tả dịch vụ + mời đặt lịch."""
    dept = DEPARTMENTS.get(code, {})
    name = dept.get("name", code)
    info = SERVICE_INFO.get(code) or dept.get("desc", "")
    sess["dept_code"] = code  # để nút "Đặt lịch" (yes) dùng ngay dịch vụ này
    text = (diag_note + f"<b>{name}</b><br>{info}<br><br>"
            "Bạn có muốn đặt lịch dịch vụ này không?")
    return reply(
        safety.add_disclaimer(text),
        options=[
            {"label": f"✅ Đặt lịch: {name}", "value": "yes"},
            {"label": "🔁 Mô tả triệu chứng của tôi", "value": "no"},
        ],
        state="CONFIRM_DEPT",
    )


def service_catalog(sess, prefix=""):
    """Trả lời "còn dịch vụ nào khác không?" — liệt kê TOÀN BỘ danh mục để chọn."""
    lines = "<br>".join(f"• <b>{d['name']}</b> <span class='muted'>— {d['desc']}</span>"
                        for d in DEPARTMENTS.values())
    options = [{"label": d["name"], "value": code} for code, d in DEPARTMENTS.items()]
    options.append({"label": "🔁 Mô tả lại triệu chứng", "value": "redo"})
    return reply(
        prefix + f"Phòng khám có <b>{len(DEPARTMENTS)} nhóm dịch vụ</b>:<br>{lines}<br><br>"
        "Bạn muốn dùng dịch vụ nào? (hoặc mô tả triệu chứng để mình gợi ý giúp)",
        options=options,
        state="CONFIRM_DEPT",
    )


def confirm_dept(sess, message):
    from . import doctor_step

    low = message.lower()

    # "còn dịch vụ nào khác không?" -> LIỆT KÊ danh mục, đừng lặp lại hướng dẫn chọn.
    if nlu.asks_other_service(message):
        return service_catalog(sess)

    # Đang chờ xác nhận ĐỔI dịch vụ (vd. vừa gọi tên bác sĩ của dịch vụ khác).
    pending = sess.get("pending_dept_code")
    if pending:
        sess["pending_dept_code"] = None
        if low in {"yes", "confirm"} or nlu.is_affirmative(message):
            sess["dept_code"] = pending
            return advance_after_dept(sess)
        if (low == "back" or nlu.is_negative(message)) and sess.get("dept_code"):
            sess["pending_doctor_id"] = None
            return doctor_step.start_doctor_pick(sess, prefix="Được, mình giữ dịch vụ cũ. ")
        sess["pending_doctor_id"] = None  # gõ thứ khác -> xử lý như bình thường

    if low in {"redo", "mô tả lại"} or nlu.is_negative(message):
        return reply("Không sao, bạn mô tả lại triệu chứng giúp mình nhé.", state="TRIAGE")

    if (low == "yes" or nlu.is_affirmative(message)) and sess["dept_code"]:
        return advance_after_dept(sess)

    # message có thể là mã dịch vụ (từ nút bấm) hoặc tên dịch vụ.
    for code, dept in DEPARTMENTS.items():
        if low == code or dept["name"].lower() in low:
            sess["dept_code"] = code
            return advance_after_dept(sess)

    # Không bấm nút mà MÔ TẢ TIẾP triệu chứng ("răng tôi còn chảy máu chân răng nữa")
    # -> triage lại trên câu mới thay vì bắt bấm nút.
    if triage.classify_symptoms(message) or triage.mentions_dental_discomfort(message) \
            or triage.negated_matches(message):
        return do_triage(sess, message)

    options = [{"label": r["name"], "value": r["code"]}
               for r in sess.get("candidates", [])[:3]]
    options.append({"label": "📋 Xem tất cả dịch vụ", "value": "còn dịch vụ nào khác"})
    options.append({"label": "🔁 Mô tả lại triệu chứng", "value": "redo"})
    return reply(
        "Bạn vui lòng chọn một dịch vụ ở các nút bên trên, gõ <b>tên dịch vụ</b>, hoặc "
        "<b>mô tả lại triệu chứng</b> nhé. Nếu không cần đặt lịch nữa, gõ <b>“thôi”</b>.",
        options=options,
        state="CONFIRM_DEPT")


def advance_after_dept(sess):
    """Sau khi chốt dịch vụ: nếu đã có bác sĩ "đặt trước" (người dùng gọi tên bác sĩ
    của dịch vụ đó) và bác sĩ này thuộc đúng dịch vụ -> xếp luôn, khỏi hỏi lại."""
    from . import doctor_step, schedule_step
    from ...booking import service as booking

    pending_doc = sess.get("pending_doctor_id")
    sess["pending_doctor_id"] = None
    if pending_doc:
        for d in booking.get_doctors(sess["dept_code"]):
            if d["id"] == pending_doc:
                sess["doctor_id"] = d["id"]
                return schedule_step.start_date_pick(
                    sess, prefix=f"Đã chọn <b>{d['name']}</b>. ")
    return doctor_step.start_doctor_pick(sess)
