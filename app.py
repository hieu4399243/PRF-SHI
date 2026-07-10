"""
AI Health Assistant (SHI) — Flask server (API cho web + app native).

Chạy:
    pip install -r requirements.txt
    python app.py
Web demo: http://127.0.0.1:5000
App native (Expo) gọi cùng các endpoint /api/*, truyền "session" trong body.
"""

import hmac
import os
import uuid
from flask import Flask, render_template, request, jsonify, session, Response, abort

import chatbot
import booking
import calendar_ics
import push
import storage

app = Flask(__name__)
# Production: đặt biến môi trường SECRET_KEY. Demo: dùng key mặc định.
app.secret_key = os.environ.get("SECRET_KEY", "shi-nha-khoa-demo-key")

# Khóa truy cập trang quản trị (admin/bác sĩ). Production: đặt ADMIN_KEY trong .env.
ADMIN_KEY = os.environ.get("ADMIN_KEY", "shi-admin-demo")

_DEFAULT_SECRET_KEY = "shi-nha-khoa-demo-key"
_DEFAULT_ADMIN_KEY = "shi-admin-demo"


def _default_key_warnings(secret_key, admin_key):
    """Trả về danh sách cảnh báo nếu SECRET_KEY/ADMIN_KEY còn giá trị demo mặc định.

    Hàm THUẦN (không print trực tiếp) để test được mà không cần reload module."""
    warnings = []
    if secret_key == _DEFAULT_SECRET_KEY:
        warnings.append("[CẢNH BÁO] SECRET_KEY đang dùng giá trị demo mặc định — "
                         "production PHẢI đặt biến môi trường SECRET_KEY (xem .env.example).")
    if admin_key == _DEFAULT_ADMIN_KEY:
        warnings.append("[CẢNH BÁO] ADMIN_KEY đang dùng giá trị demo mặc định — "
                         "production PHẢI đặt biến môi trường ADMIN_KEY (xem .env.example).")
    return warnings


for _w in _default_key_warnings(app.secret_key, ADMIN_KEY):
    print(_w)

print(f"[storage] Chế độ lưu trữ: {'Postgres/Supabase' if storage.USE_DB else 'file JSON (local)'}")


def resolve_sid(data=None):
    """Lấy session id từ body JSON (app native) hoặc cookie (web)."""
    data = data or {}
    sid = data.get("session") or session.get("sid")
    if not sid:
        sid = uuid.uuid4().hex
    session["sid"] = sid
    return sid



@app.route("/")
def index():
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex
    return render_template("index.html")


@app.route("/api/start", methods=["POST"])
def start():
    data = request.get_json(force=True, silent=True) or {}
    sid = resolve_sid(data)
    resp = chatbot.start(sid)
    resp["session"] = sid  # trả về để app native lưu lại
    return jsonify(resp)


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True, silent=True) or {}
    sid = resolve_sid(data)
    resp = chatbot.handle_message(sid, data.get("message", ""))
    resp["session"] = sid
    return jsonify(resp)


@app.route("/api/register-push", methods=["POST"])
def register_push():
    """App native gửi device push token (Expo) để nhận thông báo."""
    data = request.get_json(force=True, silent=True) or {}
    sid = resolve_sid(data)
    token = data.get("token", "")
    push.register_token(sid, token)
    return jsonify({"ok": True, "session": sid, "registered": bool(token)})


@app.route("/api/ics/<code>")
def download_ics(code):
    """Tải file lịch .ics của một lịch hẹn -> thêm vào lịch + tự nhắc.

    Chỉ chủ sở hữu (cùng session đã đặt lịch) mới tải được. Không phân biệt
    "không tồn tại" vs "không có quyền" -> luôn 404, tránh lộ thông tin mã
    lịch hẹn có tồn tại hay không (chống enumeration).
    """
    data = request.get_json(force=True, silent=True) or {}
    sid = resolve_sid(data)
    appt = booking.get_appointment(code)
    if not appt or appt.get("session") != sid:
        abort(404)
    ics = calendar_ics.build_ics(appt)
    return Response(
        ics,
        mimetype="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{code}.ics"'},
    )


# ===========================================================================
# KHU VỰC QUẢN TRỊ (admin / bác sĩ) — chỉ ĐỌC lịch đã đặt & lịch làm việc.
# Bảo vệ bằng khóa ADMIN_KEY (chỉ qua header 'X-Admin-Key'). Đây là lớp bảo vệ
# tối thiểu cho demo; production nên thay bằng đăng nhập thật + vai trò.
# ===========================================================================
def _check_admin():
    """Chỉ chấp nhận khoá qua header X-Admin-Key — query string bị log lại
    (access log, lịch sử trình duyệt, Referer) nên không còn được chấp nhận."""
    key = request.headers.get("X-Admin-Key", "")
    return hmac.compare_digest(key, ADMIN_KEY)


@app.route("/admin")
def admin_page():
    return render_template("admin.html")


@app.route("/api/admin/appointments")
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


@app.route("/api/admin/schedule")
def admin_schedule():
    """Lịch làm việc của 1 bác sĩ trong 1 ngày (khung bận/rảnh)."""
    if not _check_admin():
        abort(401)
    doctor_id = request.args.get("doctor_id", "")
    date_str = request.args.get("date", "")
    if not doctor_id or not date_str:
        return jsonify({"error": "Cần doctor_id và date"}), 400
    return jsonify({"doctor_id": doctor_id, "date": date_str,
                    "slots": booking.doctor_day_schedule(doctor_id, date_str)})


@app.route("/api/admin/meta")
def admin_meta():
    """Danh sách bác sĩ + ngày làm việc + thống kê nhanh cho trang quản trị."""
    if not _check_admin():
        abort(401)
    return jsonify({
        "doctors": booking.all_doctors(),
        "dates": booking.known_dates(),
        "summary": booking.admin_summary(),
    })


@app.route("/api/admin/cancel", methods=["POST"])
def admin_cancel():
    """Admin hủy một lịch hẹn (đổi status='cancelled')."""
    if not _check_admin():
        abort(401)
    data = request.get_json(force=True, silent=True) or {}
    appt = booking.cancel_appointment(data.get("code", ""))
    if not appt:
        return jsonify({"ok": False, "error": "Không tìm thấy lịch 'confirmed'."}), 404
    return jsonify({"ok": True, "appointment": appt})


if __name__ == "__main__":
    # host=0.0.0.0 để điện thoại trong cùng mạng Wi-Fi gọi được.
    # Dùng cổng 5001 vì macOS (AirPlay Receiver) thường chiếm cổng 5000.
    if os.environ.get("FLASK_DEBUG_WARN_SUPPRESS") != "1":
        print("[CẢNH BÁO] Đang chạy debug=True trên host=0.0.0.0 — Werkzeug interactive "
              "debugger có thể bị khai thác từ xa (RCE) nếu máy này lộ ra mạng ngoài. "
              "Production PHẢI tắt debug (đặt debug=False) hoặc bind 127.0.0.1.")
    app.run(debug=True, host="0.0.0.0", port=5001)
