"""
Conversational core — máy trạng thái điều phối hội thoại của AI Health Assistant.

Kết nối 3 khối: triage (phân khoa), booking (đặt lịch) và safety (guardrails).
Mỗi phiên (session) giữ trạng thái riêng để dẫn dắt bệnh nhân qua các bước:
    GREET -> TRIAGE -> CONFIRM_DEPT -> PICK_DOCTOR -> PICK_DATE
          -> PICK_TIME -> ASK_NAME -> CONFIRM_BOOKING -> DONE
Bất kỳ lúc nào, guardrails (cấp cứu / handoff / chặn chẩn đoán) đều được ưu tiên.
"""

import triage
import booking
import safety

# Bộ nhớ phiên (in-memory). Sản phẩm thật nên dùng Redis/DB.
SESSIONS = {}


def _new_session():
    return {
        "state": "GREET",
        "dept_code": None,
        "doctor_id": None,
        "date": None,
        "time": None,
        "patient_name": "",
        "candidates": [],  # các khoa ứng viên từ triage
    }


def get_session(session_id: str):
    if session_id not in SESSIONS:
        SESSIONS[session_id] = _new_session()
    return SESSIONS[session_id]


def reset_session(session_id: str):
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
    safety.audit(session_id, "user", message, {"state": sess["state"]})

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
    elif state == "CONFIRM_BOOKING":
        resp = _confirm_booking(sess, message)
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
        # Không nhận ra triệu chứng -> hỏi follow-up có cấu trúc.
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


def _start_time_pick(sess):
    times = booking.get_available_times(sess["date"])
    if not times:
        return _start_date_pick(sess)
    options = [{"label": t, "value": t} for t in times]
    return _reply(
        f"Các khung giờ trống ngày <b>{_format_date(sess['date'])}</b>:",
        options=options,
        state="PICK_TIME",
    )


def _pick_time(sess, message):
    times = booking.get_available_times(sess["date"])
    msg = message.strip()
    if msg in times:
        sess["time"] = msg
        return _reply(
            "Cuối cùng, cho mình xin <b>họ tên</b> của bạn để ghi vào lịch hẹn nhé "
            "(bạn có thể gõ tên).",
            state="ASK_NAME",
        )
    return _reply("Bạn chọn giúp mình một khung giờ ở các nút bên trên nhé.", state="PICK_TIME")


def _ask_name(sess, message):
    sess["patient_name"] = message[:60] if message else "Khách"
    from data import DEPARTMENTS
    dept_name = DEPARTMENTS[sess["dept_code"]]["name"]
    doctor_name = booking.get_doctor_name(sess["dept_code"], sess["doctor_id"])
    summary = (
        "Vui lòng xác nhận lịch hẹn:<br>"
        f"• <b>Bệnh nhân:</b> {sess['patient_name']}<br>"
        f"• <b>Dịch vụ:</b> {dept_name}<br>"
        f"• <b>Bác sĩ:</b> {doctor_name}<br>"
        f"• <b>Thời gian:</b> {sess['time']} ngày {_format_date(sess['date'])}"
    )
    return _reply(
        summary,
        options=[
            {"label": "✅ Xác nhận đặt lịch", "value": "confirm"},
            {"label": "❌ Hủy", "value": "cancel"},
        ],
        state="CONFIRM_BOOKING",
    )


def _confirm_booking(sess, message):
    low = message.lower()
    if low in {"cancel", "hủy", "huỷ", "không"}:
        return _reply("Đã hủy thao tác đặt lịch. Gõ <b>“làm lại”</b> nếu bạn muốn bắt đầu lại nhé.",
                      state="DONE")

    ok, payload = booking.book_appointment(
        session_id=sess.get("_id", "anon"),
        dept_code=sess["dept_code"],
        doctor_id=sess["doctor_id"],
        date_str=sess["date"],
        time_str=sess["time"],
        patient_name=sess["patient_name"],
    )
    if not ok:
        # slot vừa bị đặt mất -> quay lại chọn giờ
        return _reply(payload["error"] + " Mời bạn chọn lại khung giờ.", state="PICK_TIME")

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
def _format_date(iso: str):
    """YYYY-MM-DD -> 'Thứ X, dd/mm'."""
    from datetime import date
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return iso
    weekdays = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
    return f"{weekdays[d.weekday()]}, {d.day:02d}/{d.month:02d}"
