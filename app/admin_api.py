from flask import Blueprint, abort, jsonify, request
import secrets

from .booking import service as booking
from .core.catalog import DEPARTMENTS
from .core import auth, storage
from .core import auth

admin_api = Blueprint("admin_api", __name__, url_prefix="/api/admin")


def _check_admin():
    """Xác thực admin qua JWT token từ cookie (username/password login)."""
    user = auth.resolve_user_from_token(request.cookies.get("auth_token"))
    return bool(user and user["role"] == "admin")


@admin_api.route("/appointments")
def admin_appointments():
    if not _check_admin():
        abort(401)
    appts = booking.query_appointments(
        date=request.args.get("date") or None,
        doctor_id=request.args.get("doctor_id") or None,
        dept_code=request.args.get("dept_code") or None,
        phone=request.args.get("phone") or None,
        status=request.args.get("status") or None,
    )
    return jsonify({"appointments": appts, "count": len(appts)})


@admin_api.route("/schedule")
def admin_schedule():
    """Lịch làm việc của 1 bác sĩ trong 1 ngày (khung bận/rảnh)."""
    if not _check_admin():
        abort(401)
    doctor_id = request.args.get("doctor_id", "")
    date_str = request.args.get("date", "")
    if not doctor_id or not date_str:
        return jsonify({"error": "Cần doctor_id và date"}), 400
    return jsonify({
        "doctor_id": doctor_id,
        "date": date_str,
        "slots": booking.doctor_day_schedule(doctor_id, date_str),
    })


@admin_api.route("/meta")
def admin_meta():
    """Danh sách bác sĩ + ngày làm việc + thống kê nhanh cho trang quản trị."""
    if not _check_admin():
        abort(401)
    return jsonify({
        "doctors": booking.all_doctors(),
        "departments": [
            {"code": code, "name": info.get("name", code)}
            for code, info in DEPARTMENTS.items()
        ],
        "dates": booking.known_dates(),
        "summary": booking.admin_summary(),
    })


@admin_api.route("/cancel", methods=["POST"])
def admin_cancel():
    """Admin hủy một lịch hẹn (đổi status='cancelled')."""
    if not _check_admin():
        abort(401)
    data = request.get_json(force=True, silent=True) or {}
    appt = booking.cancel_appointment(data.get("code", ""))
    if not appt:
        return jsonify({"ok": False, "error": "Không tìm thấy lịch 'confirmed'."}), 404
    return jsonify({"ok": True, "appointment": appt})


@admin_api.route("/doctors")
def admin_doctors():
    if not _check_admin():
        abort(401)
    doctors = storage.list_admin_doctors(search=request.args.get("q") or None)
    return jsonify({"doctors": doctors, "count": len(doctors)})


@admin_api.route("/doctors", methods=["POST"])
def admin_doctors_create():
    if not _check_admin():
        abort(401)
    data = request.get_json(force=True, silent=True) or {}
    try:
        doctor = storage.create_admin_doctor(
            doctor_id=data.get("id", ""),
            name=data.get("name", ""),
            service_code=data.get("service_code", ""),
            phone=(data.get("phone") or "").strip() or None,
            email=(data.get("email") or "").strip() or None,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    # Tạo user account cho bác sĩ nếu chưa có (username = doctor_id)
    default_password = data.get("password") or "test123"
    user_created = False
    try:
        auth.create_user_account(
            username=doctor["id"],
            password=default_password,
            role="doctor",
            email=doctor.get("email"),
            phone=doctor.get("phone"),
            doctor_id=doctor["id"],
        )
        user_created = True
    except auth.UserAlreadyExistsError:
        pass  # User đã tồn tại, bỏ qua

    resp = {"ok": True, "doctor": doctor}
    if user_created:
        resp["user"] = {"username": doctor["id"], "default_password": default_password}
    return jsonify(resp), 201


@admin_api.route("/doctors/<doctor_id>", methods=["PUT"])
def admin_doctors_update(doctor_id):
    if not _check_admin():
        abort(401)
    data = request.get_json(force=True, silent=True) or {}
    try:
        doctor = storage.update_admin_doctor(
            doctor_id=doctor_id,
            name=data.get("name"),
            service_code=data.get("service_code"),
            phone=data.get("phone"),
            email=data.get("email"),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not doctor:
        return jsonify({"ok": False, "error": "Không tìm thấy bác sĩ"}), 404

    # Đồng bộ thông tin vào user account tương ứng
    user = storage.get_user_by_doctor_id(doctor_id)
    if user:
        storage.update_user_profile(
            user["id"],
            email=doctor.get("email") or None,
            phone=doctor.get("phone") or None,
            address=user.get("address"),
        )

    return jsonify({"ok": True, "doctor": doctor})


@admin_api.route("/doctors/<doctor_id>/detail")
def admin_doctor_detail(doctor_id):
    """Chi tiết đầy đủ của một bác sĩ: thông tin + tài khoản + lịch hẹn gần đây."""
    if not _check_admin():
        abort(401)
    detail = storage.get_doctor_detail(doctor_id)
    if not detail:
        return jsonify({"ok": False, "error": "Không tìm thấy bác sĩ"}), 404
    return jsonify({"ok": True, "doctor": detail})


@admin_api.route("/patients")
def admin_patients():
    if not _check_admin():
        abort(401)
    patients = storage.list_patients(search=request.args.get("q") or None)
    return jsonify({"patients": patients, "count": len(patients)})


@admin_api.route("/patients", methods=["POST"])
def admin_patients_create():
    if not _check_admin():
        abort(401)
    data = request.get_json(force=True, silent=True) or {}
    try:
        patient = storage.create_patient_profile(
            name=data.get("name", ""),
            phone=data.get("phone", ""),
            email=(data.get("email") or "").strip() or None,
            address=(data.get("address") or "").strip() or None,
            notes=(data.get("notes") or "").strip() or None,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    # Tạo / liên kết user account cho bệnh nhân (username = số điện thoại)
    default_password = data.get("password") or secrets.token_urlsafe(8)
    user_created = False
    try:
        user = auth.create_user_account(
            username=patient["phone"],
            password=default_password,
            role="guest",
            email=patient.get("email"),
            phone=patient["phone"],
            address=patient.get("address"),
            patient_id=patient["id"],
        )
        user_created = True
    except auth.UserAlreadyExistsError:
        # User với số điện thoại này đã tồn tại — chỉ liên kết
        existing_user = storage.get_user_by_username(patient["phone"])
        if existing_user:
            storage.link_user_patient(existing_user["id"], patient["id"])
        default_password = None

    resp = {"ok": True, "patient": patient}
    if user_created:
        resp["user"] = {"username": patient["phone"], "default_password": default_password}
    return jsonify(resp), 201


@admin_api.route("/patients/<patient_id>", methods=["PUT"])
def admin_patients_update(patient_id):
    if not _check_admin():
        abort(401)
    data = request.get_json(force=True, silent=True) or {}
    try:
        patient = storage.update_patient_profile_admin(
            patient_id=patient_id,
            name=data.get("name"),
            phone=data.get("phone"),
            email=data.get("email"),
            address=data.get("address"),
            notes=data.get("notes"),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not patient:
        return jsonify({"ok": False, "error": "Không tìm thấy bệnh nhân"}), 404

    # Đồng bộ thông tin vào user account tương ứng
    user = storage.get_user_by_patient_id(patient_id)
    if user:
        storage.update_user_profile(
            user["id"],
            email=patient.get("email") or None,
            phone=patient.get("phone") or None,
            address=patient.get("address") or None,
        )

    return jsonify({"ok": True, "patient": patient})


@admin_api.route("/patients/<patient_id>/detail")
def admin_patient_detail(patient_id):
    """Chi tiết đầy đủ của một bệnh nhân: thông tin hồ sơ + tài khoản + lịch sử lịch hẹn."""
    if not _check_admin():
        abort(401)
    detail = storage.get_patient_detail(patient_id)
    if not detail:
        return jsonify({"ok": False, "error": "Không tìm thấy bệnh nhân"}), 404
    return jsonify({"ok": True, "patient": detail})

# ---------------------------------------------------------------------------
# YÊU CẦU CHUYỂN TIẾP SANG NHÂN VIÊN (CB-05 / SMMG-52)
# ---------------------------------------------------------------------------
@admin_api.route("/handoffs")
def admin_handoffs():
    """Danh sách yêu cầu chuyển tiếp, mới nhất trước. ?status=new để lọc việc cần làm."""
    if not _check_admin():
        abort(401)
    items = storage.list_handoffs(status=request.args.get("status") or None)
    return jsonify({
        "handoffs": items,
        "count": len(items),
        "new_count": sum(1 for h in items if h.get("status") == "new"),
    })


@admin_api.route("/handoffs/<code>")
def admin_handoff_detail(code):
    """Chi tiết 1 yêu cầu, kèm TOÀN BỘ transcript hội thoại (AC: lịch sử chuyển kèm)."""
    if not _check_admin():
        abort(401)
    entry = storage.get_handoff(code)
    if not entry:
        return jsonify({"ok": False, "error": "Không tìm thấy yêu cầu"}), 404
    return jsonify({"ok": True, "handoff": entry})


@admin_api.route("/handoffs/<code>/handled", methods=["POST"])
def admin_handoff_handled(code):
    """Nhân viên nhận việc. Yêu cầu đã có người nhận -> 409, không ghi đè."""
    if not _check_admin():
        abort(401)
    user = auth.resolve_user_from_token(request.cookies.get("auth_token"))
    if not storage.get_handoff(code):
        return jsonify({"ok": False, "error": "Không tìm thấy yêu cầu"}), 404
    if not storage.set_handoff_handled(code, handled_by=(user or {}).get("username")):
        return jsonify({"ok": False, "error": "Yêu cầu này đã được tiếp nhận"}), 409
    return jsonify({"ok": True, "handoff": storage.get_handoff(code)})
