"""
Conversational core — máy trạng thái điều phối hội thoại của AI Health Assistant.

Kết nối 3 khối: triage (phân khoa), booking (đặt lịch) và safety (guardrails).
Mỗi phiên (session) giữ trạng thái riêng để dẫn dắt bệnh nhân qua các bước:
    GREET -> TRIAGE -> CONFIRM_DEPT -> PICK_DOCTOR -> PICK_DATE
          -> PICK_TIME -> ASK_NAME -> ASK_PHONE -> CONFIRM_BOOKING -> DONE
Bất kỳ lúc nào, guardrails (cấp cứu / handoff / chặn chẩn đoán) đều được ưu tiên.
"""

import time
import threading
from collections import OrderedDict

import triage
import booking
import safety

# Bộ nhớ phiên (in-memory). Sản phẩm thật nên dùng Redis/DB.
#
# OrderedDict được dùng làm cấu trúc LRU: mỗi lần một session được truy cập
# (get_session) hoặc reset (reset_session), nó được đưa xuống cuối (move_to_end)
# để đánh dấu "vừa hoạt động gần nhất". Khi số session chạm trần _MAX_SESSIONS,
# session ở đầu (lâu-không-hoạt-động-nhất) bị loại bỏ trước.
#
# LƯU Ý: _MAX_SESSIONS chỉ giới hạn bộ nhớ TRONG 1 PROCESS. Nếu sau này deploy
# nhiều worker process (vd `gunicorn --workers N`, N > 1), mỗi worker giữ
# SESSIONS riêng của nó -> trần bộ nhớ thực tế nhân lên theo số worker. Deploy
# nhiều THREAD trong 1 process (vd `--workers 1 --threads N`) không bị ảnh
# hưởng vì đã có _SESSIONS_LOCK bên dưới.
SESSIONS = OrderedDict()

_MAX_SESSIONS = 2000
_SESSION_TTL_SECONDS = 3600  # 1 giờ không hoạt động -> hết hạn

_SESSIONS_LOCK = threading.Lock()


def _new_session():
    return {
        "state": "GREET",
        "dept_code": None,
        "doctor_id": None,
        "date": None,
        "time": None,
        "patient_name": "",
        "patient_phone": "",
        "candidates": [],  # các khoa ứng viên từ triage
        "cancel_phone": "",  # SĐT dùng khi tra cứu để hủy lịch
        "cancel_code": None,  # mã lịch hẹn đang chờ xác nhận hủy
        "resume_booking": False,  # hủy lịch trùng xong thì đặt tiếp lịch đang dở
        "_last_seen": time.time(),  # không phải dữ liệu nghiệp vụ, chỉ dùng cho eviction
    }


def _evict_if_full_locked():
    """Loại session cũ nhất nếu đã chạm trần. Phải gọi trong lúc giữ _SESSIONS_LOCK."""
    if len(SESSIONS) >= _MAX_SESSIONS:
        SESSIONS.popitem(last=False)


def get_session(session_id: str):
    with _SESSIONS_LOCK:
        existing = SESSIONS.get(session_id)
        if existing is not None:
            if time.time() - existing["_last_seen"] <= _SESSION_TTL_SECONDS:
                existing["_last_seen"] = time.time()
                SESSIONS.move_to_end(session_id)
                return existing
            # Hết hạn -> coi như mới, tạo lại.
            del SESSIONS[session_id]

        _evict_if_full_locked()
        SESSIONS[session_id] = _new_session()
        return SESSIONS[session_id]


def reset_session(session_id: str):
    with _SESSIONS_LOCK:
        if session_id in SESSIONS:
            del SESSIONS[session_id]
        _evict_if_full_locked()
        SESSIONS[session_id] = _new_session()


def _reply(text, options=None, state=None, done=False, **extra):
    resp = {"reply": text, "options": options or [], "state": state, "done": done}
    resp.update(extra)  # vd. appointment={...} cho app native
    return resp


def greeting():
    return _reply(
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


def handle_message(session_id: str, raw_message: str):
    """Xử lý một lượt tin nhắn của bệnh nhân và trả về phản hồi của bot."""
    sess = get_session(session_id)
    sess["_id"] = session_id
    message = (raw_message or "").strip()

    # --- Ghi audit (đã ẩn PII) ---
    # State ASK_NAME: message chính là tên bệnh nhân -> mask_pii() không bắt được
    # (không phải phone/email/CCCD) -> ẩn thủ công trước khi ghi log.
    logged_message = "[TÊN ĐÃ ẨN]" if sess["state"] == "ASK_NAME" else message
    safety.audit(session_id, "user", logged_message, {"state": sess["state"]})

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
        resp = _reply(safety.EMERGENCY_MESSAGE, state=sess["state"])
        safety.audit(session_id, "bot", "[EMERGENCY]", {"flag": "emergency"})
        return resp

    # --- GUARDRAIL: yêu cầu gặp người thật (human handoff) ---
    if safety.needs_human_handoff(message):
        resp = _reply(
            "Tôi sẽ chuyển bạn tới <b>nhân viên/điều dưỡng</b> kèm toàn bộ nội dung "
            "trao đổi để được hỗ trợ trực tiếp. Vui lòng chờ trong giây lát. ☎️",
            state="HANDOFF",
        )
        sess["state"] = "HANDOFF"
        safety.audit(session_id, "bot", resp["reply"], {"flag": "handoff"})
        return resp

    # --- Ý định HỦY lịch đã đặt ("hủy lịch", "muốn hủy lịch hẹn"...) ---
    # Chỉ nhận ở bước nhập tự do; trong lúc đang đặt, "hủy" mang nghĩa hủy thao tác.
    if sess["state"] in {"TRIAGE", "CONFIRM_DEPT", "DONE"} and _is_cancel_request(message):
        resp = _start_cancel(sess)
        sess["state"] = resp["state"]
        safety.audit(session_id, "bot", resp["reply"],
                     {"state": resp["state"], "intent": "cancel"})
        return resp

    # --- Câu hỏi thông tin về dịch vụ ("X là khám gì / là gì / gồm gì") ---
    # Chỉ nhận ở các bước nhập tự do (tránh cướp lượt khi đang bấm chọn giờ/nhập tên).
    if sess["state"] in {"TRIAGE", "CONFIRM_DEPT", "DONE"}:
        info_code = triage.info_question_service(message)
        if info_code:
            resp = _describe_service(sess, info_code)
            sess["state"] = resp["state"]
            safety.audit(session_id, "bot", resp["reply"],
                         {"state": resp["state"], "intent": "info"})
            return resp

    # --- Định tuyến theo trạng thái ---
    state = sess["state"]
    if state == "GREET":
        resp = greeting()
    elif state == "TRIAGE":
        resp = _do_triage(sess, message)
    elif state == "CONFIRM_DEPT":
        resp = _confirm_dept(sess, message)
    elif state == "PICK_DOCTOR":
        resp = _pick_doctor(sess, message)
    elif state == "PICK_DATE":
        resp = _pick_date(sess, message)
    elif state == "PICK_TIME":
        resp = _pick_time(sess, message)
    elif state == "ASK_NAME":
        resp = _ask_name(sess, message)
    elif state == "ASK_PHONE":
        resp = _ask_phone(sess, message)
    elif state == "CONFIRM_BOOKING":
        resp = _confirm_booking(sess, message)
    elif state == "CANCEL_ASK_PHONE":
        resp = _cancel_ask_phone(sess, message)
    elif state == "CANCEL_PICK":
        resp = _cancel_pick(sess, message)
    elif state == "CANCEL_CONFIRM":
        resp = _cancel_confirm(sess, message)
    elif state == "DONE":
        resp = _reply(
            "Lịch hẹn của bạn đã hoàn tất. Gõ <b>“làm lại”</b> nếu muốn đặt lịch mới "
            "hoặc mô tả triệu chứng khác nhé.",
            state="DONE",
        )
    else:
        resp = greeting()

    # Lưu trạng thái mới vào phiên để lượt sau định tuyến đúng.
    if resp.get("state"):
        sess["state"] = resp["state"]
    safety.audit(session_id, "bot", resp["reply"], {"state": resp["state"]})
    return resp


# ---------------------------------------------------------------------------
# BƯỚC TRIAGE
# ---------------------------------------------------------------------------
def _do_triage(sess, message):
    # Người dùng yêu cầu chẩn đoán/kê đơn -> chặn nhưng vẫn cố định hướng khoa.
    diag_note = ""
    if safety.is_diagnosis_request(message):
        diag_note = ("Mình <b>không thể chẩn đoán bệnh hay kê đơn</b>, nhưng có thể "
                     "giúp bạn chọn đúng dịch vụ nha khoa. ")

    results = triage.classify_symptoms(message)
    conf = triage.confidence_level(results)

    if conf == "low":
        # Không trúng từ khóa dịch vụ cụ thể, NHƯNG câu vẫn cho thấy vấn đề răng
        # miệng (bộ phận + cảm giác khó chịu) -> đưa lựa chọn có cấu trúc để chốt.
        if triage.mentions_dental_discomfort(message):
            return _dental_followup(diag_note)
        # Không nhận ra gì -> hỏi follow-up có cấu trúc.
        return _reply(
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
        return _reply(
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
    return _reply(
        diag_note + "Vấn đề của bạn có thể liên quan vài dịch vụ. "
        "Bạn muốn dùng dịch vụ nào dưới đây?",
        options=options,
        state="CONFIRM_DEPT",
    )


def _dental_followup(diag_note=""):
    """Câu mơ hồ nhưng rõ là vấn đề răng miệng -> cho chọn mô tả gần nhất.

    Mỗi lựa chọn ánh xạ thẳng sang một mã dịch vụ; _confirm_dept xử lý tiếp.
    """
    return _reply(
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


def _describe_service(sess, code, diag_note=""):
    """Trả lời câu hỏi 'X là khám gì / là gì' bằng mô tả dịch vụ + mời đặt lịch."""
    from data import DEPARTMENTS, SERVICE_INFO
    dept = DEPARTMENTS.get(code, {})
    name = dept.get("name", code)
    info = SERVICE_INFO.get(code) or dept.get("desc", "")
    sess["dept_code"] = code  # để nút "Đặt lịch" (yes) dùng ngay dịch vụ này
    text = (diag_note + f"<b>{name}</b><br>{info}<br><br>"
            "Bạn có muốn đặt lịch dịch vụ này không?")
    return _reply(
        safety.add_disclaimer(text),
        options=[
            {"label": f"✅ Đặt lịch: {name}", "value": "yes"},
            {"label": "🔁 Mô tả triệu chứng của tôi", "value": "no"},
        ],
        state="CONFIRM_DEPT",
    )


def _confirm_dept(sess, message):
    low = message.lower()
    if low in {"no", "redo", "mô tả lại", "không"}:
        return _reply("Không sao, bạn mô tả lại triệu chứng giúp mình nhé.", state="TRIAGE")

    if low == "yes" and sess["dept_code"]:
        return _start_doctor_pick(sess)

    # message có thể là mã dịch vụ (từ nút bấm) hoặc tên dịch vụ.
    from data import DEPARTMENTS
    for code, dept in DEPARTMENTS.items():
        if low == code or dept["name"].lower() in low:
            sess["dept_code"] = code
            return _start_doctor_pick(sess)

    return _reply("Bạn vui lòng chọn một dịch vụ ở các nút bên trên, hoặc gõ tên dịch vụ nhé.",
                  state="CONFIRM_DEPT")


# ---------------------------------------------------------------------------
# BƯỚC ĐẶT LỊCH
# ---------------------------------------------------------------------------
def _start_doctor_pick(sess):
    doctors = booking.get_doctors(sess["dept_code"])
    from data import DEPARTMENTS
    dept_name = DEPARTMENTS[sess["dept_code"]]["name"]
    options = [{"label": d["name"], "value": d["id"]} for d in doctors]
    return _reply(
        f"Tuyệt vời! Bạn muốn đặt lịch với bác sĩ nào cho dịch vụ <b>{dept_name}</b>?",
        options=options,
        state="PICK_DOCTOR",
    )


def _pick_doctor(sess, message):
    doctors = booking.get_doctors(sess["dept_code"])
    low = message.lower()
    for d in doctors:
        if low == d["id"] or d["name"].lower() in low:
            sess["doctor_id"] = d["id"]
            return _start_date_pick(sess)
    return _reply("Bạn chọn giúp mình một bác sĩ ở các nút bên trên nhé.", state="PICK_DOCTOR")


def _start_date_pick(sess):
    dates = booking.get_available_dates()
    options = [{"label": _format_date(d), "value": d} for d in dates]
    return _reply("Bạn muốn khám vào ngày nào?", options=options, state="PICK_DATE")


def _pick_date(sess, message):
    dates = booking.get_available_dates()
    msg = message.strip()
    if msg in dates:
        sess["date"] = msg
        return _start_time_pick(sess)
    return _reply("Bạn chọn giúp mình một ngày ở các nút bên trên nhé.", state="PICK_DATE")


def _start_time_pick(sess, prefix=""):
    times = booking.get_available_times(sess["date"])
    if not times:
        return _start_date_pick(sess)
    options = [{"label": t, "value": t} for t in times]
    return _reply(
        prefix + f"Các khung giờ trống ngày <b>{_format_date(sess['date'])}</b>:",
        options=options,
        state="PICK_TIME",
    )


def _pick_time(sess, message):
    times = booking.get_available_times(sess["date"])
    msg = message.strip()
    if msg in times:
        sess["time"] = msg
        # Nếu đã có sẵn tên + SĐT (vd. chọn lại giờ sau khi slot bị chiếm) thì
        # đi thẳng tới bước xác nhận, không hỏi lại tên/số.
        if sess.get("patient_name") and sess.get("patient_phone"):
            return _ask_confirm(sess)
        return _reply(
            "Cuối cùng, cho mình xin <b>họ tên</b> của bạn để ghi vào lịch hẹn nhé "
            "(bạn có thể gõ tên).",
            state="ASK_NAME",
        )
    return _reply("Bạn chọn giúp mình một khung giờ ở các nút bên trên nhé.", state="PICK_TIME")


def _ask_confirm(sess):
    """Hiển thị bản tóm tắt lịch hẹn kèm nút xác nhận / hủy."""
    return _reply(
        _booking_summary(sess),
        options=[
            {"label": "✅ Xác nhận đặt lịch", "value": "confirm"},
            {"label": "❌ Hủy", "value": "cancel"},
        ],
        state="CONFIRM_BOOKING",
    )


def _ask_name(sess, message):
    sess["patient_name"] = message[:60] if message else "Khách"
    return _reply(
        "Cảm ơn bạn. Cho mình xin thêm <b>số điện thoại</b> để xác nhận và nhắc lịch nhé "
        "(vd. <i>0912 345 678</i>).",
        state="ASK_PHONE",
    )


def _ask_phone(sess, message):
    phone = _normalize_phone(message)
    if not phone:
        return _reply(
            "Số điện thoại chưa hợp lệ. Bạn nhập giúp mình số di động Việt Nam "
            "gồm <b>10 số</b> (bắt đầu bằng 0, vd. <i>0912345678</i>) nhé.",
            state="ASK_PHONE",
        )
    sess["patient_phone"] = phone
    return _ask_confirm(sess)


def _booking_summary(sess):
    from data import DEPARTMENTS
    dept_name = DEPARTMENTS[sess["dept_code"]]["name"]
    doctor_name = booking.get_doctor_name(sess["dept_code"], sess["doctor_id"])
    return (
        "Vui lòng xác nhận lịch hẹn:<br>"
        f"• <b>Bệnh nhân:</b> {sess['patient_name']}<br>"
        f"• <b>Điện thoại:</b> {sess['patient_phone']}<br>"
        f"• <b>Dịch vụ:</b> {dept_name}<br>"
        f"• <b>Bác sĩ:</b> {doctor_name}<br>"
        f"• <b>Thời gian:</b> {sess['time']} ngày {_format_date(sess['date'])}"
    )


def _confirm_booking(sess, message):
    low = message.lower()
    if low in {"cancel", "hủy", "huỷ", "không"}:
        return _reply("Đã hủy thao tác đặt lịch. Gõ <b>“làm lại”</b> nếu bạn muốn bắt đầu lại nhé.",
                      state="DONE")
    return _finalize_booking(sess)


def _finalize_booking(sess):
    """Ghi nhận lịch từ dữ liệu trong phiên. Dùng lại được sau khi hủy lịch trùng."""
    ok, payload = booking.book_appointment(
        session_id=sess.get("_id", "anon"),
        dept_code=sess["dept_code"],
        doctor_id=sess["doctor_id"],
        date_str=sess["date"],
        time_str=sess["time"],
        patient_name=sess["patient_name"],
        patient_phone=sess["patient_phone"],
    )
    if not ok:
        if payload.get("duplicate"):
            dup = payload["existing"]
            sess["cancel_code"] = dup["code"]
            sess["resume_booking"] = True
            return _reply(
                "⚠️ <b>Bạn đã đặt lịch vào đúng khung giờ này rồi.</b><br>"
                f"• <b>Mã lịch hẹn:</b> {dup['code']}<br>"
                f"• <b>Dịch vụ:</b> {dup['department']} — {dup['doctor']}<br>"
                f"• <b>Thời gian:</b> {dup['time']} ngày {_format_date(dup['date'])}<br><br>"
                "Bạn có muốn <b>hủy lịch đặt trước đó</b> và đặt lại không?",
                options=[
                    {"label": "🗑️ Hủy lịch cũ & đặt lại", "value": "confirm"},
                    {"label": "↩️ Giữ lịch cũ", "value": "back"},
                ],
                state="CANCEL_CONFIRM",
            )
        # slot vừa bị đặt mất -> quay lại chọn giờ (hiển thị lại các khung giờ còn trống)
        return _start_time_pick(sess, prefix=payload["error"] + " Mời bạn chọn lại khung giờ.<br><br>")

    # Bắn push xác nhận tới điện thoại của bệnh nhân (nếu app đã đăng ký token).
    import push
    tokens = push.get_tokens(sess.get("_id", "anon"))
    push.send_push(
        tokens,
        title="✅ Đặt lịch thành công",
        body=f"{payload['department']} - {payload['doctor']} lúc "
             f"{payload['time']} ngày {_format_date(payload['date'])}. Mã: {payload['code']}",
        data={"type": "booking_confirmed", "code": payload["code"]},
    )

    import calendar_ics
    gcal = calendar_ics.google_calendar_link(payload)
    ics_url = f"/api/ics/{payload['code']}"
    return _reply(
        "🎉 <b>Đặt lịch thành công!</b><br>"
        f"• <b>Mã lịch hẹn:</b> {payload['code']}<br>"
        f"• <b>Dịch vụ:</b> {payload['department']} — {payload['doctor']}<br>"
        f"• <b>Thời gian:</b> {payload['time']} ngày {_format_date(payload['date'])}<br><br>"
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


# ---------------------------------------------------------------------------
# HỦY LỊCH ĐÃ ĐẶT
# ---------------------------------------------------------------------------
# Nhận diện ý định hủy (khớp cả khi gõ thiếu dấu). Yêu cầu có "lịch/hẹn" để không
# nhầm với nút "hủy" (hủy thao tác) trong lúc đang đặt.
_CANCEL_PATTERNS = ["huy lich", "huy dat lich", "huy lich hen", "huy hen",
                    "huy cuoc hen", "muon huy", "bo lich hen", "xoa lich hen",
                    "cancel lich"]


def _is_cancel_request(message: str) -> bool:
    na = triage._strip_accents((message or "").lower())
    return any(p in na for p in _CANCEL_PATTERNS)


def _appt_label(a):
    """Nhãn ngắn gọn cho một lịch hẹn trên nút chọn."""
    return f"{a['department']} • {a['time']} {_format_date(a['date'])}"


def _start_cancel(sess):
    sess["cancel_phone"] = ""
    sess["cancel_code"] = None
    return _reply(
        "Bạn muốn <b>hủy lịch hẹn</b>. Cho mình xin <b>số điện thoại</b> đã dùng khi đặt "
        "để tra cứu nhé (vd. <i>0912345678</i>).",
        state="CANCEL_ASK_PHONE",
    )


def _cancel_ask_phone(sess, message):
    phone = _normalize_phone(message)
    if not phone:
        return _reply(
            "Số điện thoại chưa hợp lệ. Bạn nhập lại số 10 số (vd. <i>0912345678</i>) nhé.",
            state="CANCEL_ASK_PHONE",
        )
    appts = booking.upcoming_by_phone(phone)
    if not appts:
        return _reply(
            "Mình không tìm thấy lịch hẹn sắp tới nào với số này. Bạn kiểm tra lại số "
            "điện thoại, hoặc gõ <b>“làm lại”</b> để đặt lịch mới nhé.",
            state="DONE",
        )
    sess["cancel_phone"] = phone
    options = [{"label": _appt_label(a), "value": a["code"]} for a in appts]
    options.append({"label": "↩️ Không hủy nữa", "value": "back"})
    return _reply("Bạn muốn hủy lịch hẹn nào dưới đây?", options=options, state="CANCEL_PICK")


def _cancel_pick(sess, message):
    low = message.strip().lower()
    if low in {"back", "không", "khong", "thôi", "thoi"}:
        return _reply("Đã giữ nguyên lịch hẹn của bạn. Gõ <b>“làm lại”</b> nếu cần đặt lịch mới nhé.",
                      state="DONE")
    appts = booking.upcoming_by_phone(sess.get("cancel_phone", ""))
    chosen = next((a for a in appts if a["code"].lower() == low), None)
    if not chosen:
        return _reply("Bạn chọn giúp mình một lịch ở các nút bên trên nhé.", state="CANCEL_PICK")
    sess["cancel_code"] = chosen["code"]
    return _reply(
        "Bạn chắc chắn muốn <b>hủy</b> lịch hẹn này?<br>"
        f"• <b>Mã:</b> {chosen['code']}<br>"
        f"• <b>Dịch vụ:</b> {chosen['department']} — {chosen['doctor']}<br>"
        f"• <b>Thời gian:</b> {chosen['time']} ngày {_format_date(chosen['date'])}",
        options=[
            {"label": "✅ Hủy lịch này", "value": "confirm"},
            {"label": "↩️ Không hủy", "value": "back"},
        ],
        state="CANCEL_CONFIRM",
    )


def _cancel_confirm(sess, message):
    low = message.strip().lower()
    resume = sess.get("resume_booking", False)
    if low in {"back", "không", "khong", "thôi", "thoi", "cancel"}:
        sess["cancel_code"] = None
        sess["resume_booking"] = False
        if resume:
            # Đang đặt lịch mà gặp trùng, chọn GIỮ lịch cũ -> không tạo thêm lịch trùng.
            return _reply(
                "Được, mình <b>giữ nguyên lịch cũ</b> và không đặt thêm lịch trùng nhé. "
                "Gõ <b>“làm lại”</b> nếu bạn muốn đặt một lịch khác.",
                state="DONE",
            )
        return _reply("Đã giữ nguyên lịch hẹn. Gõ <b>“làm lại”</b> nếu cần nhé.", state="DONE")

    appt = booking.cancel_appointment(sess.get("cancel_code")) if sess.get("cancel_code") else None
    sess["cancel_code"] = None
    if not appt:
        sess["resume_booking"] = False
        return _reply(
            "Lịch hẹn này không còn để hủy (có thể đã được hủy trước đó). "
            "Gõ <b>“làm lại”</b> nếu cần nhé.",
            state="DONE",
        )

    if resume:
        # Đã hủy lịch cũ (giải phóng khung giờ) -> đặt tiếp lịch đang dở, không bắt làm lại.
        sess["resume_booking"] = False
        return _finalize_booking(sess)

    # Hủy chủ động: báo push + xác nhận đã hủy.
    import push
    tokens = push.get_tokens(sess.get("_id", "anon"))
    push.send_push(
        tokens,
        title="🗑️ Đã hủy lịch hẹn",
        body=f"{appt['department']} lúc {appt['time']} ngày {_format_date(appt['date'])} đã được hủy.",
        data={"type": "booking_cancelled", "code": appt["code"]},
    )
    return _reply(
        "✅ <b>Đã hủy lịch hẹn.</b><br>"
        f"Mã {appt['code']} — {appt['department']} lúc {appt['time']} ngày "
        f"{_format_date(appt['date'])} đã được hủy, khung giờ này đã trống trở lại.<br>"
        "<i>Gõ “làm lại” nếu bạn muốn đặt lịch mới.</i>",
        state="DONE",
    )


# ---------------------------------------------------------------------------
import re

_PHONE_RE = re.compile(r"^0\d{9}$")


def _normalize_phone(raw: str):
    """Chuẩn hóa & kiểm tra SĐT di động VN. Trả chuỗi 10 số (0xxxxxxxxx) hoặc "" nếu sai.

    Chấp nhận có khoảng trắng/dấu chấm/gạch, và đầu số +84/84 -> quy về 0xxxxxxxxx.
    """
    digits = re.sub(r"[\s.\-()]", "", raw or "")
    if digits.startswith("+84"):
        digits = "0" + digits[3:]
    elif digits.startswith("84") and len(digits) == 11:
        digits = "0" + digits[2:]
    return digits if _PHONE_RE.match(digits) else ""


def _format_date(iso: str):
    """YYYY-MM-DD -> 'Thứ X, dd/mm'."""
    from datetime import date
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return iso
    weekdays = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
    return f"{weekdays[d.weekday()]}, {d.day:02d}/{d.month:02d}"
