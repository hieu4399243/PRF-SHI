from flask import Blueprint, abort, jsonify, request

from .booking import service as booking
from .core import auth, storage

admin_api = Blueprint("admin_api", __name__, url_prefix="/api/admin")


def _check_admin():
    """Xác thực admin qua:
    JWT token từ cookie (username/password login).
    """
    # Chỉ chấp nhận JWT token từ cookie.
    token = request.cookies.get("auth_token")
    if token:
        try:
            payload = auth.verify_jwt(token)
            user = storage.get_user_by_id(payload["sub"])
            if user and user["role"] == "admin":
                return True
        except Exception:
            pass
    return False


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