"""
Bộ định tuyến hội thoại — cửa vào duy nhất của chatbot.

`handle_message()` chạy theo đúng thứ tự này, và THỨ TỰ LÀ CÓ CHỦ ĐÍCH:

    1. ghi audit (đã ẩn PII)
    2. lệnh tiện ích ("làm lại")
    3. GUARDRAIL cấp cứu          <- ưu tiên cao nhất, cắt ngang mọi bước
    4. GUARDRAIL chuyển người thật
    5. ý định hủy lịch / dừng đặt lịch
    6. câu hỏi thông tin dịch vụ
    7. chặn yêu cầu chẩn đoán
    8. định tuyến theo `state` tới module bước tương ứng (steps/)

Mỗi bước nằm ở `steps/`; module này chỉ điều phối, không chứa nội dung câu trả lời.
"""

from ..triage import nlu, safety
from .. import triage
from .reply import reply
from .session import SESSIONS, get_session, reset_session  # noqa: F401  (re-export)
from .steps import (cancel_step, confirm_step, doctor_step, handoff_step,
                    schedule_step, triage_step)

# Các bước có thể "dừng giữa chừng" (xem stop_booking).
_STOPPABLE_STATES = {"TRIAGE", "CONFIRM_DEPT", "PICK_DOCTOR", "PICK_DATE",
                     "PICK_TIME", "CONFIRM_BOOKING"}

# state -> hàm xử lý lượt tin nhắn của bước đó.
_HANDLERS = {
    "TRIAGE": triage_step.do_triage,
    "CONFIRM_DEPT": triage_step.confirm_dept,
    "PICK_DOCTOR": doctor_step.pick_doctor,
    "PICK_DATE": schedule_step.pick_date,
    "PICK_TIME": schedule_step.pick_time,
    "ASK_NAME": confirm_step.ask_name,
    "ASK_PHONE": confirm_step.ask_phone,
    "CONFIRM_BOOKING": confirm_step.confirm_booking,
    "CANCEL_ASK_PHONE": cancel_step.cancel_ask_phone,
    "CANCEL_PICK": cancel_step.cancel_pick,
    "CANCEL_CONFIRM": cancel_step.cancel_confirm,
    # Đang chờ nhân viên: PHẢI có handler riêng, nếu không lượt kế tiếp rơi vào
    # nhánh `else` bên dưới và bệnh nhân bị chào lại như phiên mới (CB-05).
    "HANDOFF": handoff_step.handoff_wait,
    "HANDOFF_ASK_CONTACT": handoff_step.handoff_ask_contact,
    "HANDOFF_OFFER": handoff_step.handoff_offer,
}


# Số lượt người dùng giữ lại làm ngữ cảnh cho llm_reply.answer().
_MAX_USER_TURNS = 5

# Ở các bước này, tin nhắn CHÍNH LÀ dữ liệu định danh -> không lưu vào phiên.
_PII_INPUT_STATES = {"ASK_NAME", "ASK_PHONE", "CANCEL_ASK_PHONE",
                     "HANDOFF_ASK_CONTACT"}


def _remember_turn(sess, message):
    """Ghi lượt vừa rồi của người dùng để bước sau còn hiểu câu tham chiếu ngược."""
    if not message or sess["state"] in _PII_INPUT_STATES:
        return
    turns = sess.setdefault("user_turns", [])
    turns.append(message)
    del turns[:-_MAX_USER_TURNS]


def stop_booking(message):
    """Người dùng dừng đặt lịch. Nếu vì đã đỡ thì chúc mừng, kèm dặn dò an toàn."""
    if nlu.recovered(message):
        text = ("Rất mừng vì bạn đã đỡ hơn 💚 Vậy mình <b>không đặt lịch</b> nữa nhé.<br>"
                "Nếu triệu chứng quay lại hoặc kéo dài, bạn nên đi khám để nha sĩ kiểm "
                "tra trực tiếp — gõ <b>“làm lại”</b> là mình đặt lịch ngay.")
    else:
        text = ("Được, mình <b>dừng việc đặt lịch</b> ở đây nhé. Khi nào cần, bạn gõ "
                "<b>“làm lại”</b> để bắt đầu lại.")
    return reply(text, state="DONE")


def greeting():
    return reply(
        "Xin chào 👋 Tôi là <b>Trợ lý Nha khoa SHI</b>.<br>"
        "Tôi giúp bạn <b>chọn đúng dịch vụ nha khoa</b> phù hợp và <b>đặt lịch hẹn</b>.<br><br>"
        "Bạn đang gặp vấn đề gì về răng miệng? (ví dụ: <i>“răng tôi bị sâu và ê buốt khi ăn ngọt”</i>)"
        + safety.DISCLAIMER,
        state="TRIAGE",
    )


def start(session_id: str):
    """Khởi tạo phiên mới và trả về lời chào (đặt sẵn trạng thái TRIAGE)."""
    reset_session(session_id)
    sess = get_session(session_id)
    sess["_id"] = session_id
    resp = greeting()
    sess["state"] = resp["state"]
    safety.audit(session_id, "bot", resp["reply"], {"state": resp["state"]})
    return resp


def start_with_service(session_id: str, dept_code: str):
    """Mở phiên đặt lịch với dịch vụ ĐÃ CHỌN SẴN — nút "Đặt lịch ngay" ở card gợi ý.

    Bỏ qua bước TRIAGE và vào thẳng chọn nha sĩ: bệnh nhân đã chọn dịch vụ trên
    card thì hỏi lại triệu chứng là bắt họ làm lại việc vừa làm (TC-REC-003: "không
    cần chọn lại dịch vụ").

    Mã dịch vụ lạ -> quay về lời chào bình thường, KHÔNG lỗi: card gợi ý có thể là
    bản cũ trong tab đang mở, còn danh mục thì đã đổi.
    """
    from ..core.catalog import DEPARTMENTS

    reset_session(session_id)
    sess = get_session(session_id)
    sess["_id"] = session_id

    if dept_code not in DEPARTMENTS:
        resp = greeting()
    else:
        sess["dept_code"] = dept_code
        dept_name = DEPARTMENTS[dept_code]["name"]
        resp = doctor_step.start_doctor_pick(
            sess,
            prefix=f"Bạn đang đặt lịch cho dịch vụ <b>{dept_name}</b> (từ gợi ý "
                   "điều trị).<br>",
        )
    sess["state"] = resp["state"]
    safety.audit(session_id, "bot", resp["reply"],
                 {"state": resp["state"], "intent": "reco_book"})
    return resp


def handle_message(session_id: str, raw_message: str):
    """Xử lý một lượt tin nhắn của bệnh nhân và trả về phản hồi của bot."""
    sess = get_session(session_id)
    with sess["_lock"]:
        sess["_id"] = session_id
        message = (raw_message or "").strip()

        # --- Ghi audit (đã ẩn PII) ---
        # State ASK_NAME: message chính là tên bệnh nhân -> mask_pii() không bắt được
        # (không phải phone/email/CCCD) -> ẩn thủ công trước khi ghi log.
        logged_message = "[TÊN ĐÃ ẨN]" if sess["state"] == "ASK_NAME" else message
        safety.audit(session_id, "user", logged_message, {"state": sess["state"]})
        _remember_turn(sess, message)

        # --- Lệnh tiện ích ---
        low = message.lower()
        if low in {"/reset", "bắt đầu lại", "làm lại"}:
            reset_session(session_id)
            sess = get_session(session_id)
            sess["_id"] = session_id
            resp = greeting()
            sess["state"] = resp["state"]
            safety.audit(session_id, "bot", resp["reply"], {"state": resp["state"]})
            return resp

        # --- GUARDRAIL ưu tiên cao nhất: CẤP CỨU ---
        if safety.check_emergency(message):
            resp = reply(safety.EMERGENCY_MESSAGE, state=sess["state"])
            safety.audit(session_id, "bot", "[EMERGENCY]", {"flag": "emergency"})
            return resp

        # --- GUARDRAIL: yêu cầu gặp người thật (human handoff) ---
        # Lớp TỪ KHOÁ, cố ý giữ dù đã có lớp ngữ nghĩa trong llm_reply.answer():
        # đây là đường thoát sang người thật, không được phụ thuộc API bên thứ ba.
        # Bỏ qua khi ĐANG ở luồng handoff (đã chuyển rồi, đừng tạo yêu cầu trùng).
        if sess["state"] not in {"HANDOFF", "HANDOFF_ASK_CONTACT"} \
                and safety.needs_human_handoff(message):
            resp = handoff_step.start_handoff(sess, handoff_step.PATIENT_REQUEST)
            sess["state"] = resp["state"]
            safety.audit(session_id, "bot", resp["reply"],
                         {"state": resp["state"], "flag": "handoff",
                          "handoff_code": sess.get("handoff_code")})
            return resp

        # --- Ý định HỦY lịch đã đặt ("hủy lịch", "muốn hủy lịch hẹn"...) ---
        # Chỉ nhận ở bước nhập tự do; trong lúc đang đặt, "hủy" mang nghĩa hủy thao tác.
        if sess["state"] in {"TRIAGE", "CONFIRM_DEPT", "DONE"} \
                and cancel_step.is_cancel_request(message):
            resp = cancel_step.start_cancel(sess)
            sess["state"] = resp["state"]
            safety.audit(session_id, "bot", resp["reply"],
                         {"state": resp["state"], "intent": "cancel"})
            return resp

        # --- Ý định DỪNG ("thôi tôi không bị nữa", "hết đau rồi", "để hôm khác") ---
        # Chỉ nhận ở các bước đang dẫn dắt đặt lịch. KHÔNG nhận ở ASK_NAME/ASK_PHONE
        # (câu trả lời ở đó là tên/SĐT, không phải ý định) và ở luồng CANCEL_*
        # (nơi "thôi" đã mang nghĩa "không hủy nữa").
        if sess["state"] in _STOPPABLE_STATES and nlu.wants_stop(message):
            resp = stop_booking(message)
            sess["state"] = resp["state"]
            safety.audit(session_id, "bot", resp["reply"],
                         {"state": resp["state"], "intent": "stop"})
            return resp

        # --- Câu hỏi thông tin về dịch vụ ("X là khám gì / là gì / gồm gì") ---
        # Chỉ nhận ở các bước nhập tự do (tránh cướp lượt khi đang bấm chọn giờ/nhập tên).
        if sess["state"] in {"TRIAGE", "CONFIRM_DEPT", "DONE"}:
            info_code = triage.info_question_service(message)
            if info_code:
                resp = triage_step.describe_service(sess, info_code)
                sess["state"] = resp["state"]
                safety.audit(session_id, "bot", resp["reply"],
                             {"state": resp["state"], "intent": "info"})
                return resp

        # --- Chặn yêu cầu chẩn đoán ngoài TRIAGE (TRIAGE tự xử lý inline trong
        # do_triage, không lặp lại ở đây) ---
        if sess["state"] != "TRIAGE" and safety.is_diagnosis_request(message):
            resp = reply(
                "Mình không thể chẩn đoán bệnh hay kê đơn thuốc nhé. Mình có thể giúp "
                "bạn chọn đúng dịch vụ nha khoa và đặt lịch khám — bạn tiếp tục ở bước "
                "hiện tại nha.",
                state=sess["state"],
            )
            safety.audit(session_id, "bot", resp["reply"], {"flag": "diagnosis_request"})
            return resp

        # --- Định tuyến theo trạng thái ---
        state = sess["state"]
        handler = _HANDLERS.get(state)
        if handler:
            resp = handler(sess, message)
        elif state == "GREET":
            # start() luôn đặt state=TRIAGE, nên GREET ở đây nghĩa là phiên đã MẤT:
            # server restart (SESSIONS in-memory), hết TTL, hoặc request rơi vào
            # worker khác. Đừng NUỐT tin nhắn của người dùng — nếu nó đã là mô tả
            # triệu chứng thì triage luôn, chỉ chào lại khi thật sự không hiểu.
            if triage.classify_symptoms(message) or triage.mentions_dental_discomfort(message):
                resp = triage_step.do_triage(sess, message)
            else:
                resp = greeting()
        elif state == "DONE":
            resp = reply(
                "Lịch hẹn của bạn đã hoàn tất. Gõ <b>“làm lại”</b> nếu muốn đặt lịch mới "
                "hoặc mô tả triệu chứng khác nhé.",
                state="DONE",
            )
        else:
            resp = greeting()

        # Hội thoại NHÍCH được sang bước khác -> bot không còn loay hoay, xoá bộ
        # đếm "bó tay" (llm_reply.is_stuck). Các nhánh fallback luôn trả về đúng
        # state cũ, nên "state đổi" là dấu hiệu tiến triển đủ tin cậy.
        if resp.get("state") and resp["state"] != state:
            sess["stuck_turns"] = 0

        # Lưu trạng thái mới vào phiên để lượt sau định tuyến đúng.
        if resp.get("state"):
            sess["state"] = resp["state"]
        safety.audit(session_id, "bot", resp["reply"], {"state": resp["state"]})
        return resp
