"""
AI Health Assistant (SHI) — Flask server (API cho web + app native).

Chạy:
    pip install -r requirements.txt
    python app.py
Web demo: http://127.0.0.1:5000
App native (Expo) gọi cùng các endpoint /api/*, truyền "session" trong body.
"""

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
    """Tải file lịch .ics của một lịch hẹn -> thêm vào lịch + tự nhắc."""
    appt = booking.get_appointment(code)
    if not appt:
        abort(404)
    ics = calendar_ics.build_ics(appt)
    return Response(
        ics,
        mimetype="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{code}.ics"'},
    )


if __name__ == "__main__":
    # host=0.0.0.0 để điện thoại trong cùng mạng Wi-Fi gọi được.
    # Dùng cổng 5001 vì macOS (AirPlay Receiver) thường chiếm cổng 5000.
    app.run(debug=True, host="0.0.0.0", port=5001)
