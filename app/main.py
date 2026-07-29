"""
AI Health Assistant (SHI) — Flask server (API cho web + app native).

Chạy:
    pip install -r requirements.txt
    python app.py
Web demo: http://127.0.0.1:5000
App native (Expo) gọi cùng các endpoint /api/*, truyền "session" trong body.
"""

import os
import re
import threading
import time
import uuid
from collections import OrderedDict
from flask import Flask, render_template, request, jsonify, session, Response, abort, redirect

from . import chatbot
from .admin_api import admin_api
from .doctor_api import doctor_api
from .booking import calendar_ics
from .booking import service as booking
from .core import storage
from .core import auth
from .notify import push

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # 64KB — đủ rộng cho tin nhắn text, chặn DoS
# Production: đặt biến môi trường SECRET_KEY. Demo: dùng key mặc định.
app.secret_key = os.environ.get("SECRET_KEY", "shi-nha-khoa-demo-key")

_DEFAULT_SECRET_KEY = "shi-nha-khoa-demo-key"
app.register_blueprint(admin_api)
app.register_blueprint(doctor_api)


def _default_key_warnings(secret_key):
    """Trả về danh sách cảnh báo nếu SECRET_KEY còn giá trị demo mặc định.

    Hàm THUẦN (không print trực tiếp) để test được mà không cần reload module."""
    warnings = []
    if secret_key == _DEFAULT_SECRET_KEY:
        warnings.append("[CẢNH BÁO] SECRET_KEY đang dùng giá trị demo mặc định — "
                         "production PHẢI đặt biến môi trường SECRET_KEY (xem .env.example).")
    return warnings


for _w in _default_key_warnings(app.secret_key):
    print(_w)

print(f"[storage] Chế độ lưu trữ: {'Postgres/Supabase' if storage.USE_DB else 'file JSON (local)'}")


_SID_RE = re.compile(r"^[0-9a-f]{32}$")


def require_auth(allowed_roles=None):
    """Decorator để protect endpoints — kiểm tra JWT token từ cookie.

    Args:
        allowed_roles: list của roles được phép (vd. ['admin', 'doctor']).
                      Nếu None, chỉ cần login (bất kỳ role).

    Returns:
        Decorator function

    Usage:
        @app.route("/api/admin/something")
        @require_auth(allowed_roles=['admin'])
        def admin_only():
            user = request.current_user
            return jsonify({"user_id": user["id"]})
    """
    from functools import wraps

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = auth.resolve_user_from_token(request.cookies.get("auth_token"))
            if not user:
                return jsonify({"error": "Chưa login"}), 401

            # Check role nếu cần
            if allowed_roles and user["role"] not in allowed_roles:
                return jsonify({"error": "Không có quyền truy cập"}), 403

            # Lưu user info vào request context
            request.current_user = user
            return func(*args, **kwargs)

        return wrapper

    return decorator


def resolve_sid(data=None):
    """Lấy session id từ body JSON (app native) hoặc cookie (web).

    Giá trị client gửi trong body phải đúng định dạng uuid4-hex (32 ký tự hex
    thường) — sai định dạng bị bỏ qua, coi như không gửi, tránh session id
    đoán được/cố định do client tự chọn tuỳ ý.
    """
    data = data or {}
    client_sid = data.get("session")
    if client_sid and (not isinstance(client_sid, str) or not _SID_RE.match(client_sid)):
        client_sid = None
    sid = client_sid or session.get("sid")
    if not sid:
        sid = uuid.uuid4().hex
    session["sid"] = sid
    return sid


_RATE_LOCK = threading.Lock()
_RATE_BUCKETS = OrderedDict()  # ip -> list[timestamp], LRU-cap giống SESSIONS ở chatbot.py
_RATE_LIMIT = 30          # request
_RATE_WINDOW = 60         # giây
_RATE_MAX_IPS = 5000      # trần số IP theo dõi, tránh unbounded growth


def _is_rate_limited(ip):
    now = time.time()
    with _RATE_LOCK:
        bucket = _RATE_BUCKETS.get(ip)
        if bucket is None:
            if len(_RATE_BUCKETS) >= _RATE_MAX_IPS:
                _RATE_BUCKETS.popitem(last=False)  # loại IP cũ nhất
            bucket = []
            _RATE_BUCKETS[ip] = bucket
        else:
            _RATE_BUCKETS.move_to_end(ip)
        bucket[:] = [t for t in bucket if now - t < _RATE_WINDOW]
        if len(bucket) >= _RATE_LIMIT:
            return True
        bucket.append(now)
        return False


@app.before_request
def _rate_limit_guard():
    if not request.path.startswith("/api/"):
        return None  # trang web (/, /admin) không giới hạn
    if _is_rate_limited(request.remote_addr or "unknown"):
        return jsonify({"error": "Quá nhiều yêu cầu, vui lòng thử lại sau."}), 429
    return None



@app.route("/")
def index():
    """Chatbot page — guest & authorized users can access."""
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex
    return render_template("index.html")


@app.route("/login")
def login_page():
    """Trang login — auto redirect nếu đã login."""
    user = auth.resolve_user_from_token(request.cookies.get("auth_token"))
    if user and user["role"] == "admin":
        return redirect("/admin")
    elif user and user["role"] == "doctor":
        return redirect("/doctor-dashboard")
    return render_template("login.html")


@app.route("/doctor-dashboard")
@require_auth(allowed_roles=["doctor"])
def doctor_dashboard():
    """Trang dashboard cho doctor."""
    user = request.current_user
    if not user.get("doctor_id"):
        return jsonify({"error": "Tài khoản doctor chưa gán doctor_id"}), 400
    return render_template("doctor.html")


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


@app.route("/admin")
def admin_page():
    user = auth.resolve_user_from_token(request.cookies.get("auth_token"))
    if not user or user.get("role") != "admin":
        return redirect("/login")
    return render_template("admin.html")


# ===========================================================================
# AUTHENTICATION API
# ===========================================================================
@app.route("/api/login", methods=["POST"])
def api_login():
    """Login với username/password. Trả về JWT token để lưu vào cookie."""
    data = request.get_json(force=True, silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username và password bắt buộc"}), 400

    try:
        result = auth.login(username, password)
        # Lưu token vào cookie (httponly để JS không truy cập được, bảo mật hơn)
        resp = jsonify({
            "ok": True,
            "user": result["user"],
            "message": f"Chào mừng {result['user']['username']}!"
        })
        resp.set_cookie(
            "auth_token",
            result["token"],
            httponly=True,
            secure=os.environ.get("SECURE_COOKIE", "false").lower() == "true",  # True cho HTTPS
            samesite="Lax",  # chống CSRF
            max_age=24 * 60 * 60,  # 24 giờ
        )
        return resp
    except auth.InvalidCredentialsError:
        return jsonify({"error": "Username hoặc password sai"}), 401
    except storage.UserStoreUnavailableError:
        print("[auth] api_login lỗi: user store cần DATABASE_URL nhưng chưa cấu hình")
        return jsonify({"error": "Lỗi hệ thống, vui lòng thử lại sau."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/logout", methods=["POST"])
def api_logout():
    """Logout — xoá JWT token khỏi cookie."""
    resp = jsonify({"ok": True, "message": "Đã đăng xuất"})
    resp.set_cookie(
        "auth_token",
        "",
        httponly=True,
        secure=os.environ.get("SECURE_COOKIE", "false").lower() == "true",
        samesite="Lax",
        max_age=0,  # expire ngay lập tức
    )
    return resp


@app.route("/api/register", methods=["POST"])
def api_register():
    """Tạo user mới (admin-only hoặc self-service tuỳ config).

    Để cho đơn giản, ở đây cho phép bất kỳ ai tạo user mới (guest signup).
    Nếu muốn chỉ admin tạo, kiểm tra JWT token trước.
    """
    data = request.get_json(force=True, silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    email = data.get("email", "").strip()
    role = data.get("role", "guest")  # mặc định 'guest', có thể là 'admin' hoặc 'doctor'
    doctor_id = data.get("doctor_id")  # chỉ cho role='doctor'

    # Validate
    if not username or not password:
        return jsonify({"error": "Username và password bắt buộc"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password phải tối thiểu 6 ký tự"}), 400
    if role not in ["guest", "doctor"]:
        return jsonify({"error": "Role không hợp lệ"}), 400

    if role == "doctor":
        if not doctor_id or not any(d["id"] == doctor_id for d in booking.all_doctors()):
            return jsonify({"error": "doctor_id không hợp lệ"}), 400
        try:
            if storage.get_user_by_doctor_id(doctor_id):
                return jsonify({"error": "doctor_id đã được đăng ký"}), 409
        except storage.UserStoreUnavailableError:
            pass  # để create_user_account bên dưới raise lỗi rõ ràng (đã bắt riêng phía dưới)

    try:
        user = auth.create_user_account(
            username=username,
            password=password,
            role=role,
            email=email if email else None,
            doctor_id=doctor_id,
        )
        return jsonify({
            "ok": True,
            "user": user,
            "message": f"Tạo user '{username}' thành công! Vui lòng login."
        }), 201
    except auth.UserAlreadyExistsError as e:
        return jsonify({"error": str(e)}), 409
    except storage.UserStoreUnavailableError:
        print("[auth] api_register lỗi: user store cần DATABASE_URL nhưng chưa cấu hình")
        return jsonify({"error": "Lỗi hệ thống, vui lòng thử lại sau."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/me", methods=["GET"])
def api_me():
    """Lấy thông tin user hiện tại từ JWT token."""
    user = auth.resolve_user_from_token(request.cookies.get("auth_token"))
    if not user:
        return jsonify({"error": "Chưa login"}), 401
    return jsonify({
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "email": user.get("email"),
            "doctor_id": user.get("doctor_id"),
        }
    })


if __name__ == "__main__":
    # host=0.0.0.0 để điện thoại trong cùng mạng Wi-Fi gọi được.
    # Dùng cổng 5001 vì macOS (AirPlay Receiver) thường chiếm cổng 5000.
    if os.environ.get("FLASK_DEBUG_WARN_SUPPRESS") != "1":
        print("[CẢNH BÁO] Đang chạy debug=True trên host=0.0.0.0 — Werkzeug interactive "
              "debugger có thể bị khai thác từ xa (RCE) nếu máy này lộ ra mạng ngoài. "
              "Production PHẢI tắt debug (đặt debug=False) hoặc bind 127.0.0.1.")
    app.run(debug=True, host="0.0.0.0", port=5001)
