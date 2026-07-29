from flask import Blueprint, abort, jsonify, request

from .booking import service as booking
from .core import auth


doctor_api = Blueprint("doctor_api", __name__, url_prefix="/api/doctor")


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
    return jsonify({"appointments": appts, "count": len(appts)})


@doctor_api.route("/schedule")
def doctor_schedule():
    user = _get_current_doctor()
    if not user:
        abort(401)

    date_str = request.args.get("date", "")
    if not date_str:
        return jsonify({"error": "Cần date"}), 400

    doctor_id = user["doctor_id"]
    return jsonify({
        "doctor_id": doctor_id,
        "date": date_str,
        "slots": booking.doctor_day_schedule(doctor_id, date_str),
    })
