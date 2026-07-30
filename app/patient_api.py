"""
API cho trang bệnh nhân — PAT-01 (tổng quan + lịch sử) và REC-01/02 (gợi ý).

Hai chế độ:

  - **Đã đăng nhập** (role='patient'): lịch sử, lịch hẹn, gợi ý cá nhân hoá, và
    hành động (bỏ qua gợi ý) được lưu bền.
  - **Khách chưa đăng nhập**: vẫn xem được trang gợi ý, nhưng hệ thống chưa biết là
    ai nên luôn rơi vào nhánh cold-start (dịch vụ phổ biến). Không đọc được lịch
    sử/lịch hẹn của bất kỳ ai, và không ghi được gì bền. Khách vẫn đặt lịch qua
    widget chatbot như trước.

Nguyên tắc bảo mật của cả blueprint: **không endpoint nào nhận `patient_id` từ
client**. Định danh luôn lấy từ JWT trong cookie, nên bệnh nhân A không thể đọc dữ
liệu của bệnh nhân B bằng cách đổi tham số — và khách thì không có định danh nào để
đọc dữ liệu người khác.

Đường dẫn dùng tiền tố `/api/patient/*` (spec PAT-01 ghi `/api/v1/patient/...`,
nhưng toàn bộ endpoint hiện có của dự án đều là `/api/*` không version — xem §11
docs/patient-recommendation-design.md).
"""

from flask import Blueprint, jsonify, request

from . import reco
from .core import auth, storage
from .core.catalog import DEPARTMENTS

patient_api = Blueprint("patient_api", __name__, url_prefix="/api/patient")

# Hành động của bệnh nhân trên gợi ý (enum RecommendationLog.patient_action).
PATIENT_ACTIONS = ("book", "dismiss", "skip_all", "view_detail", "no_action")


def current_patient():
    """Bệnh nhân đang đăng nhập, hoặc None. Không raise khi thiếu DB/token."""
    user = auth.resolve_user_from_token(request.cookies.get("auth_token"))
    if not user or user.get("role") != "patient":
        return None
    return user


def _clinical(user):
    """Hồ sơ lâm sàng của bệnh nhân (bảng `patients`), rỗng nếu chưa liên kết.

    Tài khoản đăng nhập (`users`) và hồ sơ bệnh nhân (`patients`) là hai thực thể
    khác nhau — nối với nhau qua `users.patient_id`. Tuổi và dị ứng nằm ở hồ sơ,
    vì một bệnh nhân có thể tồn tại trước khi có tài khoản đăng nhập.
    """
    return storage.get_patient_clinical(user.get("patient_id")) or {}


def _profile(user):
    """Phần hồ sơ mà engine cần: tuổi + dị ứng."""
    clinical = _clinical(user)
    return {"birth_year": clinical.get("birth_year"),
            "allergies": clinical.get("allergies") or []}


def _patient_refs(user):
    """Cặp (patient_id, phone) để gộp lịch sử trước và sau khi có hồ sơ.

    `patient_id` là khoá hồ sơ bệnh nhân (không phải `users.id`). SĐT lấy từ hồ sơ,
    fallback về SĐT trên tài khoản — lịch hẹn đặt qua chatbot chỉ có SĐT.
    """
    clinical = _clinical(user)
    return user.get("patient_id"), clinical.get("phone") or user.get("phone")


@patient_api.route("/me")
def me():
    user = current_patient()
    if not user:
        return jsonify({"is_guest": True, "full_name": None, "username": None,
                        "birth_year": None, "visit_count": 0, "has_history": False})
    patient_id, phone = _patient_refs(user)
    history = reco.history.recent(patient_id=patient_id, patient_phone=phone)
    return jsonify({
        "is_guest": False,
        "full_name": _clinical(user).get("name") or user["username"],
        "username": user["username"],
        "birth_year": _clinical(user).get("birth_year"),
        "visit_count": len(history),
        "has_history": bool(history),
    })


@patient_api.route("/history")
def history():
    """Bảng lịch sử sử dụng dịch vụ (AC PAT-01: ngày, dịch vụ, bác sĩ, trạng thái)."""
    user = current_patient()
    if not user:
        # Khách: không có định danh -> không có lịch sử nào để trả, và tuyệt đối
        # không được trả lịch sử của người khác.
        return jsonify({"history": [], "count": 0, "is_guest": True})
    patient_id, phone = _patient_refs(user)

    doctor_names = {}
    from .core.catalog import DOCTORS
    for docs in DOCTORS.values():
        for d in docs:
            doctor_names[d["id"]] = d["name"]

    rows = []
    for rec in reco.history.recent(patient_id=patient_id, patient_phone=phone):  # noqa: E501
        rows.append({
            "date": rec.get("treatment_date"),
            "service_code": rec.get("service_code"),
            "service_name": DEPARTMENTS.get(rec.get("service_code"), {}).get(
                "name", rec.get("service_code")),
            "doctor": doctor_names.get(rec.get("doctor_id")) or "—",
            "outcome": rec.get("outcome"),
            "followup_due_date": rec.get("followup_due_date"),
        })
    return jsonify({"history": rows, "count": len(rows), "is_guest": False})


# LƯU Ý: endpoint lịch hẹn của bệnh nhân nằm ở `main.py`
# (`GET /api/patient/appointments`, bản của nhánh quản lý BN) — khớp theo session
# + SĐT hồ sơ. Không định nghĩa lại ở đây, hai rule cùng đường dẫn sẽ che nhau.


@patient_api.route("/recommendations")
def recommendations():
    """Top-3 gợi ý dịch vụ (REC-01) kèm dữ liệu cho màn chi tiết (REC-02).

    Khách chưa đăng nhập vẫn gọi được: không truyền định danh nào -> engine thấy
    `visit_count = 0` -> nhánh cold-start (dịch vụ phổ biến). Đây là hành vi đúng,
    không phải trường hợp lỗi.
    """
    user = current_patient()
    trigger = request.args.get("trigger") or "booking_page"

    if not user:
        result = reco.recommend(trigger=trigger)
    else:
        patient_id, phone = _patient_refs(user)
        result = reco.recommend(patient_id=patient_id, patient_phone=phone,
                                profile=_profile(user), trigger=trigger)
    result["is_guest"] = not user

    # Không trả `signals` ra ngoài: đó là nội bộ engine (trọng số từng luật), bệnh
    # nhân chỉ cần `reason_text` + `reason_detail`.
    items = [{k: v for k, v in item.items() if k != "signals"}
             for item in result["items"]]
    return jsonify({**result, "items": items})


@patient_api.route("/recommendations/action", methods=["POST"])
def recommendation_action():
    """Ghi hành động của bệnh nhân trên gợi ý (book / dismiss / skip_all / view_detail).

    `dismiss` lưu BỀN vào patient_preference: TC-REC-004 yêu cầu dịch vụ đã bỏ qua
    không xuất hiện lại ở những lần sau.
    """
    user = current_patient()
    data = request.get_json(force=True, silent=True) or {}
    action = (data.get("action") or "").strip()
    if action not in PATIENT_ACTIONS:
        return jsonify({"error": "Hành động không hợp lệ"}), 400

    service_code = data.get("service_code")
    if service_code is not None and service_code not in DEPARTMENTS:
        return jsonify({"error": "Dịch vụ không hợp lệ"}), 400

    rank = data.get("rank")
    try:
        rank = int(rank) if rank is not None else None
    except (TypeError, ValueError):
        rank = None

    dismissed = None
    if action == "dismiss":
        if not service_code:
            return jsonify({"error": "Cần service_code khi bỏ qua gợi ý"}), 400
        patient_id = _patient_refs(user)[0] if user else None
        if patient_id:
            dismissed = storage.add_dismissed_service(patient_id, service_code)
        # Khách: không có tài khoản để gắn lựa chọn -> không lưu được bền.
        # `dismissed = None` cho UI biết mà chỉ ẩn card trong phiên hiện tại.

    logged = False
    if data.get("rec_log_id"):
        # Gợi ý của khách không được ghi log (engine bỏ qua khi không có
        # patient_id), nên record_action sẽ trả False — đúng, không phải lỗi.
        logged = reco.record_action(data["rec_log_id"], action, service_code, rank)

    return jsonify({"ok": True, "logged": logged, "dismissed": dismissed,
                    "is_guest": not user})


@patient_api.route("/recommendations/reset", methods=["POST"])
def reset_dismissed():
    """Bỏ toàn bộ đánh dấu "Không quan tâm" (link reset ở empty state, TC-REC-005)."""
    user = current_patient()
    if not user:
        return jsonify({"error": "Chưa đăng nhập"}), 401
    storage.reset_dismissed_services(_patient_refs(user)[0])
    return jsonify({"ok": True})
