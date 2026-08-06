from datetime import date, datetime

from flask import Blueprint, abort, jsonify, request

from . import reco
from .booking import service as booking
from .core import auth, storage
from .core.catalog import DEPARTMENTS


doctor_api = Blueprint("doctor_api", __name__, url_prefix="/api/doctor")

# Kết quả điều trị — §6.3 docs/patient-recommendation-design.md (cột `outcome`).
TREATMENT_OUTCOMES = ("success", "partial", "failed")


def _get_current_doctor():
    """Xác thực doctor từ JWT cookie và trả về user object."""
    user = auth.resolve_user_from_token(request.cookies.get("auth_token"))
    if not user or user.get("role") != "doctor" or not user.get("doctor_id"):
        return None
    return user


def _doctor_profile(doctor_id):
    for d in booking.all_doctors():
        if d.get("id") == doctor_id:
            return d
    return {"id": doctor_id, "name": doctor_id, "dept_code": "", "dept_name": ""}


def _recorded_appointment_codes():
    """Mã lịch hẹn đã có bản ghi điều trị. Rỗng nếu chưa cấu hình được storage —
    bảng vẫn hiện được, chỉ mất dấu "đã ghi"."""
    try:
        return {t.get("appointment_code") for t in storage.list_treatments()
                if t.get("appointment_code")}
    except Exception as exc:  # noqa: BLE001
        print(f"[doctor] Không đọc được lịch sử điều trị: {exc}")
        return set()


def _treatment_blocker(appt, doctor_id, recorded_codes):
    """Lý do KHÔNG ghi được kết quả cho lịch hẹn này, hoặc None nếu ghi được.

    Dùng chung cho `/appointments` (quyết định có hiện nút không) và `/treatment`
    (chốt chặn thật). Tách ra vì bản đầu để client tự đoán điều kiện: nút hiện lên
    cho cả lịch mang mã khoa cũ (`ho_hap`, `tieu_hoa` — di sản từ thời dự án còn
    là phòng khám đa khoa), bấm vào chỉ nhận 400.

    Trả (mã_lỗi, thông_điệp) — mã dùng cho UI, thông điệp trả thẳng cho người dùng.
    """
    if appt.get("code") in recorded_codes:
        return "da_ghi", "Lịch hẹn này đã được ghi nhận trước đó"
    if appt.get("doctor_id") != doctor_id:
        return "khong_phai_cua_ban", "Lịch hẹn không thuộc về bạn"
    if appt.get("status") != "confirmed":
        return "chua_xac_nhan", "Chỉ ghi nhận được lịch hẹn đang ở trạng thái confirmed"
    if (appt.get("date") or "") > date.today().isoformat():
        return "chua_toi_ngay", "Lịch hẹn chưa tới ngày"
    if appt.get("department_code") not in DEPARTMENTS:
        return "dich_vu_da_bo", "Dịch vụ của lịch hẹn không còn trong danh mục"
    return None, None


def _with_treatment_flags(appt, doctor_id, recorded_codes):
    """Lịch hẹn + cờ cho UI: đã ghi kết quả chưa, ghi được không, vướng gì."""
    blocker, _msg = _treatment_blocker(appt, doctor_id, recorded_codes)
    return {**appt,
            "treatment_recorded": appt.get("code") in recorded_codes,
            "can_record_treatment": blocker is None,
            "record_blocker": blocker}


def _doctor_known_dates(doctor_id):
    dates = {a.get("date") for a in booking.query_appointments(doctor_id=doctor_id) if a.get("date")}
    dates.update(booking.get_available_dates())
    return sorted(dates, reverse=True)


@doctor_api.route("/meta")
def doctor_meta():
    user = _get_current_doctor()
    if not user:
        abort(401)

    doctor_id = user["doctor_id"]
    doctor_appts = booking.query_appointments(doctor_id=doctor_id)
    summary = {
        "total": len(doctor_appts),
        "confirmed": sum(1 for a in doctor_appts if a.get("status") == "confirmed"),
        "cancelled": sum(1 for a in doctor_appts if a.get("status") == "cancelled"),
    }

    return jsonify({
        "doctor": _doctor_profile(doctor_id),
        "dates": _doctor_known_dates(doctor_id),
        "summary": summary,
    })


@doctor_api.route("/appointments")
def doctor_appointments():
    user = _get_current_doctor()
    if not user:
        abort(401)

    appts = booking.query_appointments(
        date=request.args.get("date") or None,
        doctor_id=user["doctor_id"],
        phone=request.args.get("phone") or None,
        status=request.args.get("status") or None,
    )
    # Server quyết định lịch nào ghi được kết quả, client chỉ hiển thị. Để client
    # tự suy thì nút mời bấm rồi trả 400/409 — chính là lỗi nha sĩ gặp trên bảng
    # lịch hẹn có mã khoa cũ.
    recorded = _recorded_appointment_codes()
    doctor_id = user["doctor_id"]
    out = [_with_treatment_flags(a, doctor_id, recorded) for a in appts]
    return jsonify({"appointments": out, "count": len(out)})


@doctor_api.route("/schedule")
def doctor_schedule():
    user = _get_current_doctor()
    if not user:
        abort(401)

    date_str = request.args.get("date", "")
    if not date_str:
        return jsonify({"error": "Cần date"}), 400

    doctor_id = user["doctor_id"]
    # Cùng bộ cờ với bảng lịch hẹn: nha sĩ làm việc theo lưới giờ trong ngày, nên
    # ghi kết quả ngay tại slot vừa khám xong là đường đi tự nhiên hơn việc quay
    # sang tab khác tìm đúng mã lịch.
    recorded = _recorded_appointment_codes()
    slots = []
    for slot in booking.doctor_day_schedule(doctor_id, date_str):
        appt = slot.get("appt")
        slots.append({**slot,
                      "appt": _with_treatment_flags(appt, doctor_id, recorded)
                      if appt else None})
    return jsonify({"doctor_id": doctor_id, "date": date_str, "slots": slots})


# ===========================================================================
# GHI NHẬN LƯỢT ĐIỀU TRỊ (§6.4 docs/patient-recommendation-design.md)
# ===========================================================================
def _valid_iso_date(value):
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


def _patient_id_of_appointment(appt):
    """Hồ sơ bệnh nhân mà lượt điều trị này thuộc về — None nếu không chắc.

    Ưu tiên TUYỆT ĐỐI **tài khoản đã đặt lịch** (`appointments.booked_by_user_id`,
    đóng dấu lúc đặt từ JWT, client không truyền được). Đặt lịch hộ bằng SĐT của
    người khác là hợp lệ, nên SĐT KHÔNG đủ để nói lịch này thuộc về ai: gõ nhầm
    một chữ số là ca khám chui vào bệnh án của chủ số đó. Đã xảy ra thật —
    `SHI-ELBICD` đặt bằng SĐT ...769 nên ca trám răng rơi vào hồ sơ tài khoản khác.

    Chỉ khi lịch đặt bởi KHÁCH (không có tài khoản) mới rơi về suy theo SĐT — lúc
    đó SĐT là định danh duy nhất tồn tại, và không có tài khoản nào để gán nhầm.
    """
    user_id = appt.get("booked_by_user_id")
    if user_id:
        try:
            user = storage.get_user_by_id(user_id)
        except Exception as exc:  # noqa: BLE001
            print(f"[doctor] Không tra được tài khoản đặt lịch: {exc}")
            user = None
        # Tài khoản đã đặt lịch nhưng chưa có hồ sơ bệnh nhân -> None, bản ghi neo
        # theo SĐT. Không được rơi xuống nhánh SĐT bên dưới: tài khoản đã xác định
        # rồi thì SĐT trên lịch hẹn không còn quyền nói lịch này của ai.
        return (user or {}).get("patient_id")
    return _resolve_patient_id(appt.get("patient_phone"))


def _resolve_patient_id(phone):
    """Hồ sơ bệnh nhân (bảng `patients`) theo SĐT — None nếu chưa có hồ sơ.

    CHỈ dùng cho lịch hẹn đặt bởi khách chưa đăng nhập (xem
    `_patient_id_of_appointment`). Không có hồ sơ vẫn ghi lịch sử được: engine gộp
    theo (patient_id OR phone), nên lượt điều trị của người đặt qua chatbot vẫn
    đếm vào `visit_count` khi họ đăng ký tài khoản sau này.
    """
    if not phone:
        return None
    try:
        for p in storage.list_patients(search=phone):
            if (p.get("phone") or "").strip() == phone:
                return p.get("id")
    except Exception as exc:  # noqa: BLE001 - thiếu DB thì vẫn neo theo SĐT
        print(f"[doctor] Không tra được hồ sơ bệnh nhân theo SĐT: {exc}")
    return None


@doctor_api.route("/treatment", methods=["POST"])
def record_treatment():
    """Nha sĩ đánh dấu một lịch hẹn ĐÃ KHÁM XONG -> ghi 1 dòng `treatment_history`.

    Đây là mắt xích nối `appointments` (app ghi khi đặt lịch) với
    `treatment_history` (engine gợi ý đọc). Thiếu nó thì `visit_count` của mọi
    bệnh nhân đứng yên ở 0 và màn gợi ý vĩnh viễn ở cold-start —
    `scripts/backfill_treatment_history.py` chỉ vá được dữ liệu cũ một lần.

    Body: `appointment_code` (bắt buộc), `outcome`, `followup_required`,
    `followup_due_date`, `patient_rating`.
    """
    user = _get_current_doctor()
    if not user:
        abort(401)

    data = request.get_json(force=True, silent=True) or {}
    code = (data.get("appointment_code") or "").strip()
    if not code:
        return jsonify({"error": "Cần appointment_code"}), 400

    appt = next((a for a in booking.query_appointments() if a.get("code") == code), None)
    if not appt:
        return jsonify({"error": "Không tìm thấy lịch hẹn"}), 404

    # Cùng bộ luật với cờ `can_record_treatment` ở `/appointments` -> nút trên
    # dashboard không bao giờ mời bấm một việc endpoint sẽ từ chối.
    #   403 = lịch của nha sĩ khác (chốt chặn: lịch sử điều trị lái thẳng vào gợi
    #   ý y tế, không cho ai bịa hộ người khác)
    #   409 = đã ghi rồi
    #   400 = các trường hợp còn lại
    blocker, message = _treatment_blocker(appt, user["doctor_id"],
                                          _recorded_appointment_codes())
    if blocker == "khong_phai_cua_ban":
        return jsonify({"error": message}), 403
    if blocker == "da_ghi":
        return jsonify({"error": message}), 409
    if blocker:
        return jsonify({"error": message}), 400

    treatment_date = appt.get("date") or ""
    service_code = appt.get("department_code")

    outcome = (data.get("outcome") or "success").strip()
    if outcome not in TREATMENT_OUTCOMES:
        return jsonify({"error": f"outcome phải thuộc {list(TREATMENT_OUTCOMES)}"}), 400

    followup_required = bool(data.get("followup_required"))
    followup_due_date = (data.get("followup_due_date") or "").strip() or None
    # `followup_required` nghĩa là "nha sĩ ĐÃ HẸN tái khám" — một chỉ định của
    # người. Không tự suy ngày từ `recurring_months`: làm thế thì luật
    # `followup_due` (tín hiệu mạnh nhất của engine) sẽ nói sai bản chất, đúng lý
    # do backfill cố tình để trống trường này.
    if followup_required and not followup_due_date:
        return jsonify({"error": "Cần followup_due_date khi hẹn tái khám"}), 400
    if followup_due_date and not _valid_iso_date(followup_due_date):
        return jsonify({"error": "followup_due_date phải có dạng YYYY-MM-DD"}), 400
    if not followup_required:
        followup_due_date = None

    rating = data.get("patient_rating")
    if rating is not None:
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            return jsonify({"error": "patient_rating phải là số nguyên 1..5"}), 400
        if not 1 <= rating <= 5:
            return jsonify({"error": "patient_rating phải là số nguyên 1..5"}), 400

    phone = appt.get("patient_phone") or None
    added = storage.add_treatment({
        # Cùng quy ước id với backfill -> một lịch hẹn đã backfill thì ghi tay
        # cũng không tạo bản ghi trùng.
        "history_id": f"th-{code}",
        "appointment_code": code,
        "patient_id": _patient_id_of_appointment(appt),
        "patient_phone": phone,
        "service_code": service_code,
        "doctor_id": user["doctor_id"],
        "treatment_date": treatment_date,
        "outcome": outcome,
        "followup_required": followup_required,
        "followup_due_date": followup_due_date,
        "patient_rating": rating,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    })
    if not added:
        return jsonify({"error": "Lịch hẹn này đã được ghi nhận trước đó"}), 409

    return jsonify({"ok": True, "appointment_code": code,
                    "service_code": service_code,
                    "treatment_date": treatment_date}), 201


# ===========================================================================
# HỒ SƠ BỆNH NHÂN PHÍA NHA SĨ (trigger `dentist_view` — §8 doc thiết kế)
# ===========================================================================
def _doctor_names():
    return {d.get("id"): d.get("name") for d in booking.all_doctors()}


def _treatment_rows(patient_id, phone):
    """Lịch sử điều trị đã làm giàu để hiển thị: tên dịch vụ + tên nha sĩ."""
    names = _doctor_names()
    rows = []
    for rec in reco.history.recent(patient_id=patient_id, patient_phone=phone):
        rows.append({
            "date": rec.get("treatment_date"),
            "service_code": rec.get("service_code"),
            "service_name": DEPARTMENTS.get(rec.get("service_code"), {}).get(
                "name", rec.get("service_code")),
            "doctor": names.get(rec.get("doctor_id")) or rec.get("doctor_id") or "—",
            "outcome": rec.get("outcome"),
            "followup_due_date": rec.get("followup_due_date"),
        })
    return rows


@doctor_api.route("/patient")
def doctor_patient_detail():
    """Hồ sơ + lịch sử điều trị + gợi ý dịch vụ của MỘT bệnh nhân, cho nha sĩ xem.

    Đây là chỗ duy nhất dùng trigger `dentist_view`: cùng engine với màn bệnh nhân,
    nhưng đọc bằng con mắt nha sĩ ngay trong lúc khám. `visit_count` < 3 thì gợi ý
    vẫn ở nhánh cold-start — đúng thiết kế, và cũng là cách nha sĩ thấy được vì sao
    phải ghi đủ kết quả khám.

    Định danh nhận vào là SĐT chứ không phải `patient_id`: lịch hẹn đặt qua chatbot
    chỉ có SĐT, và SĐT là thứ duy nhất nối được lịch hẹn với hồ sơ. Nha sĩ CHỈ xem
    được bệnh nhân đã từng có lịch hẹn với chính mình — không thì endpoint này
    thành cửa tra cứu toàn bộ bệnh nhân của phòng khám bằng cách dò số.
    """
    user = _get_current_doctor()
    if not user:
        abort(401)

    phone = (request.args.get("phone") or "").strip()
    if not phone:
        return jsonify({"error": "Cần phone"}), 400

    doctor_id = user["doctor_id"]
    appts = booking.query_appointments(doctor_id=doctor_id, phone=phone)
    if not appts:
        return jsonify({"error": "Bệnh nhân này chưa từng có lịch hẹn với bạn"}), 403

    patient_id = _resolve_patient_id(phone)
    clinical = storage.get_patient_clinical(patient_id) if patient_id else {}
    name = (clinical.get("name")
            or next((a.get("patient_name") for a in reversed(appts)
                     if a.get("patient_name")), "")
            or "Bệnh nhân")

    treatments = _treatment_rows(patient_id, phone)
    result = reco.recommend(
        patient_id=patient_id, patient_phone=phone,
        profile={"birth_year": clinical.get("birth_year"),
                 "allergies": clinical.get("allergies") or []},
        trigger="dentist_view")

    # `signals` là trọng số nội bộ của bộ luật, không phải thông tin lâm sàng —
    # giữ nguyên ranh giới mà `/api/patient/recommendations` đã đặt.
    items = [{k: v for k, v in item.items() if k != "signals"}
             for item in result["items"]]

    return jsonify({
        "patient": {"name": name, "phone": phone, "patient_id": patient_id,
                    "birth_year": clinical.get("birth_year")},
        "visit_count": len(treatments),
        "treatments": treatments,
        "appointment_count": len(appts),
        "recommendations": {**result, "items": items},
    })
