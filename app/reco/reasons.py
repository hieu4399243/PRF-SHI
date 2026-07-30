"""
Sinh câu lý do từ `reason_code` — bước 5.3 của SEQ ("reason_text from template").

TC-REC-006 đặt ra hai yêu cầu, và cả hai đều được test:
  1. Người dùng thường đọc hiểu được.
  2. KHÔNG chứa thuật ngữ kỹ thuật (CF, CBF, embedding, score, model...).

Đây cũng là tầng fallback khi LLM bị tắt/lỗi/trả câu không hợp lệ (xem
reco/llm_reason.py). Template luôn phải đứng vững một mình.
"""

from ..core.catalog import DEPARTMENTS, service_meta

# Từ ngữ KHÔNG được xuất hiện trong câu lý do gửi cho bệnh nhân. Dùng cho cả
# template (test) lẫn kiểm duyệt đầu ra của LLM.
BANNED_TERMS = (
    "cf", "cbf", "embedding", "vector", "score", "model", "confidence",
    "collaborative", "filtering", "tf-idf", "svd", "cosine", "ai model",
    "thuật toán", "trọng số", "điểm số",
)

MAX_REASON_LENGTH = 120

# Câu lý do KHẲNG ĐỊNH điều gì đó về bệnh tật/thuốc = chẩn đoán, tuyệt đối không
# được gửi cho bệnh nhân.
#
# Vì sao không dùng lại `safety.is_diagnosis_request()`: bộ pattern đó được xây để
# bắt câu HỎI của người dùng ("tôi bị bệnh gì", "uống thuốc gì"), nên nó không bắt
# được câu KHẲNG ĐỊNH do LLM sinh ra ("Bạn bị viêm tủy, cần uống kháng sinh").
# Đây là hai bài toán khác chiều, cần hai bộ chặn.
MEDICAL_CLAIM_TERMS = (
    "bạn bị", "bạn đang bị", "bạn có bệnh", "chẩn đoán", "bệnh lý",
    "viêm", "nhiễm trùng", "ung thư", "áp xe", "sâu răng nặng",
    "thuốc", "kháng sinh", "kê đơn", "liều", "giảm đau",
    "chắc chắn khỏi", "khỏi hẳn", "đảm bảo khỏi", "chữa khỏi",
)


def _service_name(code):
    return DEPARTMENTS.get(code, {}).get("name", code)


def _thang(n):
    """Diễn đạt số tháng cho người đọc, tránh '0 tháng' hay '18 tháng'."""
    n = int(n or 0)
    if n <= 0:
        return "gần đây"
    if n == 1:
        return "1 tháng"
    if n < 12:
        return f"{n} tháng"
    years = n // 12
    rest = n % 12
    if rest == 0:
        return f"{years} năm"
    return f"{years} năm {rest} tháng"


def render(signal):
    """Câu lý do NGẮN cho một tín hiệu. Luôn trả về chuỗi không rỗng."""
    code = signal.get("service_code")
    ctx = signal.get("ctx") or {}
    name = _service_name(code)
    reason_code = signal.get("reason_code")

    if reason_code == "followup_due":
        months = ctx.get("months_since")
        if months:
            return (f"Đã {_thang(months)} kể từ lần {name.lower()} gần nhất — "
                    "đã tới hạn kiểm tra lại.")
        return "Lịch tái khám nha sĩ hẹn cho bạn đã tới hạn."

    if reason_code == "past_treatment":
        cycle = ctx.get("cycle")
        months = ctx.get("months_since")
        # "MỖI khoảng X tháng" chứ không phải "sau khoảng X tháng": bản cũ tối
        # nghĩa và bị LLM đọc thành "hẹn lại sau X tháng nữa" — đổi hẳn ý nghĩa.
        return (f"Bạn từng dùng dịch vụ này {_thang(months)} trước; "
                f"dịch vụ này nên làm lại mỗi khoảng {cycle} tháng.")

    if reason_code == "care_pathway":
        from_name = _service_name(ctx.get("from_service")).lower()
        return f"Sau khi {from_name}, bước chăm sóc tiếp theo thường là dịch vụ này."

    if reason_code == "similar_patients":
        percent = ctx.get("percent", 0)
        from_name = _service_name(ctx.get("from_service")).lower()
        return (f"{percent}% bệnh nhân từng {from_name} cũng đã dùng dịch vụ này.")

    if reason_code == "age_group":
        return "Dịch vụ phù hợp với nhóm tuổi của bạn."

    if reason_code == "popular":
        return "Dịch vụ được nhiều bệnh nhân của phòng khám lựa chọn."

    return "Dịch vụ có thể phù hợp với bạn."


def _format_date(iso):
    """YYYY-MM-DD -> dd/mm/yyyy."""
    try:
        y, m, d = iso.split("-")
        return f"{d}/{m}/{y}"
    except (AttributeError, ValueError):
        return iso


def context_line(item, features):
    """Dòng DỮ KIỆN mở đầu phần "Tại sao AI gợi ý?" — mốc thời gian cụ thể.

    Các câu lý do khác nói về LUẬT ("tới hạn làm lại", "bệnh nhân tương tự");
    dòng này nói về DỮ LIỆU của chính bệnh nhân, để họ đối chiếu được thay vì phải
    tin lời hệ thống. Wireframe REC-02 mở đầu bằng đúng dòng dạng này.
    """
    if not features:
        return None
    # Ưu tiên mốc của CHÍNH dịch vụ đang xem; không có thì mốc khám gần nhất.
    last = (features.get("last_by_service") or {}).get(item.get("service_code"))
    label = "Lần dùng dịch vụ này gần nhất"
    if not last:
        last = features.get("last_treatment_date")
        label = "Lần khám gần nhất"
    if not last:
        return None

    months = _months_between(features.get("today"), last)
    if months is None:
        return f"{label}: {_format_date(last)}."
    return f"{label}: {_format_date(last)} — đã qua {_thang(months)}."


def _months_between(today_iso, iso):
    from datetime import date
    try:
        delta = date.fromisoformat(today_iso) - date.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    return int(delta.days // 30.44)


def render_all(item, features=None):
    """Danh sách lý do cho màn chi tiết REC-02 ("Tại sao AI gợi ý?").

    Dòng đầu là dữ kiện thời gian (nếu có), sau đó là từng tín hiệu theo thứ tự
    mạnh dần xuống. Không trùng lặp.
    """
    seen, out = set(), []
    fact = context_line(item, features)
    if fact:
        seen.add(fact)
        out.append(fact)
    for signal in item.get("signals") or []:
        text = render(signal)
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out


def cold_start_note():
    """Câu giải thích cho state cold-start (wireframe state 4)."""
    return ("Chưa có đủ dữ liệu để gợi ý cá nhân hoá. Đang hiển thị các dịch vụ "
            "phổ biến — sau lần khám đầu, gợi ý sẽ sát với bạn hơn.")


EMPTY_STATE_TEXT = ("Không còn gợi ý phù hợp. Chúng tôi sẽ cập nhật sau khi có "
                    "thêm dữ liệu.")


def has_banned_term(text):
    """Câu lý do có lọt thuật ngữ kỹ thuật không? (TC-REC-006)"""
    low = (text or "").lower()
    return any(term in low for term in BANNED_TERMS)


def has_medical_claim(text):
    """Câu lý do có khẳng định về bệnh/thuốc/kết quả điều trị không?

    Cố ý CHẶT: gợi ý chỉ được nói về DỊCH VỤ và lịch sử sử dụng dịch vụ. Thà loại
    oan một câu hay rồi quay về template, hơn là để một câu chẩn đoán tới bệnh nhân.
    """
    low = (text or "").lower()
    return any(term in low for term in MEDICAL_CLAIM_TERMS)


def service_payload(code):
    """Phần thông tin dịch vụ đi kèm mỗi gợi ý (card + modal chi tiết REC-02)."""
    dept = DEPARTMENTS.get(code, {})
    meta = service_meta(code)
    return {
        "service_code": code,
        "name": dept.get("name", code),
        "desc": dept.get("desc", ""),
        "duration_min": meta["duration_min"],
        "price_from": meta["price_from"],
        "price_to": meta["price_to"],
    }
