"""
Lớp an toàn (safety layer) — yếu tố phân biệt chatbot y tế thật với bot thường.

Gồm:
  - Input guardrail : lọc/ẩn PII, phát hiện dấu hiệu cấp cứu.
  - Output guardrail : đảm bảo bot KHÔNG chẩn đoán / KHÔNG kê đơn, thêm disclaimer.
  - Human handoff    : phát hiện tình huống cần chuyển nhân viên thật.
  - Audit log        : ghi lại toàn bộ hội thoại (tuân thủ Nghị định 13/2023).
"""

import re
import json
import os
import threading
from datetime import datetime, timezone

from triage import _normalize, _strip_accents, _contains_word

AUDIT_LOG_PATH = os.path.join(os.path.dirname(__file__), "audit_log.jsonl")
AUDIT_LOG_MAX_BYTES = 5 * 1024 * 1024  # 5MB, 1 thế hệ xoay vòng (đủ cho demo/đồ án)

_AUDIT_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# 1) PHÁT HIỆN CẤP CỨU  -> hướng dẫn gọi 115, không tư vấn tiếp.
# ---------------------------------------------------------------------------
_SEED_EMERGENCY_PATTERNS = [
    # Cấp cứu chung (đe dọa tính mạng)
    "đau ngực dữ dội", "đau thắt ngực", "khó thở nặng", "không thở được",
    "ngất", "bất tỉnh", "co giật", "tai biến", "đột quỵ",
    "liệt nửa người", "chảy máu không cầm", "ho ra máu", "nôn ra máu",
    "tự tử", "muốn chết", "tự làm hại", "khó thở dữ dội", "tím tái",
    "đau ngực lan ra tay", "hôn mê",
    # Cấp cứu nha khoa / hàm mặt
    "sưng mặt lan", "sưng mặt to", "sưng to cả mặt", "khó nuốt", "khó há miệng",
    "sốt cao kèm sưng", "chảy máu không ngừng sau nhổ răng", "máu chảy không ngừng",
    "gãy xương hàm", "chấn thương hàm mặt", "răng bị văng ra", "rụng nguyên cái răng",
    "tai nạn gãy răng",
]

EMERGENCY_MESSAGE = (
    "⚠️ <b>Đây có thể là tình huống CẤP CỨU.</b><br>"
    "Vui lòng gọi ngay <b>115</b> (cấp cứu) hoặc đến cơ sở y tế gần nhất. "
    "Tôi là trợ lý ảo và không thể xử lý tình huống khẩn cấp."
)

# ---------------------------------------------------------------------------
# 2) LỌC PII  (Personally Identifiable Information)
#    Ẩn số điện thoại, email, số CCCD trước khi ghi log / gửi đi xử lý.
# ---------------------------------------------------------------------------
PII_PATTERNS = [
    (re.compile(r"\b(0|\+84)\d{8,10}\b"), "[SĐT]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
    (re.compile(r"\b\d{9,12}\b"), "[CCCD/CMND]"),
]


def mask_pii(text: str) -> str:
    """Thay thế thông tin định danh cá nhân bằng nhãn ẩn."""
    masked = text
    for pattern, label in PII_PATTERNS:
        masked = pattern.sub(label, masked)
    return masked


# ---------------------------------------------------------------------------
# 3) CHẶN YÊU CẦU CHẨN ĐOÁN / KÊ ĐƠN  -> chuyển hướng an toàn.
# ---------------------------------------------------------------------------
_SEED_DIAGNOSIS_REQUEST_PATTERNS = [
    "tôi bị bệnh gì", "bị bệnh gì", "chẩn đoán", "có phải ung thư",
    "uống thuốc gì", "kê đơn", "dùng thuốc gì", "thuốc nào", "liều lượng",
    "có nguy hiểm không", "có sao không", "đơn thuốc",
]

# Từ khóa cho biết người dùng muốn gặp NHÂN VIÊN THẬT (human handoff).
_SEED_HANDOFF_PATTERNS = [
    "gặp người", "nhân viên", "tư vấn viên", "gọi cho tôi",
    "khiếu nại", "không hài lòng", "nói chuyện với người thật",
]


# ---------------------------------------------------------------------------
# NẠP BỘ PATTERN: Supabase (nguồn chính) + seed trong code (fail-safe).
# Guardrail là dữ liệu AN TOÀN nên KHÔNG bao giờ để trống: nếu DB không có / một
# nhóm rỗng / lỗi kết nối -> tự dùng seed baseline của nhóm đó. DB chỉ MỞ RỘNG.
# Quản lý online tại Supabase bảng `safety_patterns` (kind, pattern).
# ---------------------------------------------------------------------------
def _load_patterns():
    seeds = {
        "emergency": _SEED_EMERGENCY_PATTERNS,
        "diagnosis": _SEED_DIAGNOSIS_REQUEST_PATTERNS,
        "handoff": _SEED_HANDOFF_PATTERNS,
    }
    db = {}
    try:
        import storage
        if storage.USE_DB:
            db = storage.list_safety_patterns() or {}
    except Exception:
        db = {}  # lỗi DB/mạng -> dùng seed, KHÔNG để guardrail biến mất
    # Mỗi nhóm ưu tiên DB; nhóm nào rỗng -> fallback seed (không bao giờ để trống).
    return {kind: (db.get(kind) or seed) for kind, seed in seeds.items()}


_PATTERNS = _load_patterns()
EMERGENCY_PATTERNS = _PATTERNS["emergency"]
DIAGNOSIS_REQUEST_PATTERNS = _PATTERNS["diagnosis"]
HANDOFF_PATTERNS = _PATTERNS["handoff"]

DISCLAIMER = (
    "<br><span class='disclaimer'>ℹ️ Lưu ý: Tôi chỉ hỗ trợ chọn dịch vụ nha khoa "
    "và đặt lịch, <b>không chẩn đoán bệnh và không kê đơn thuốc</b>. "
    "Chẩn đoán chính xác cần nha sĩ thăm khám trực tiếp.</span>"
)


def check_emergency(text: str) -> bool:
    """Trả về True nếu phát hiện dấu hiệu cấp cứu (bắt cả câu không dấu)."""
    norm_na = _strip_accents(_normalize(text))
    return any(
        _contains_word(norm_na, _strip_accents(_normalize(p)))
        for p in EMERGENCY_PATTERNS
    )


def is_diagnosis_request(text: str) -> bool:
    """Người dùng đang yêu cầu chẩn đoán / kê đơn? (bắt cả câu không dấu)"""
    norm_na = _strip_accents(_normalize(text))
    return any(
        _contains_word(norm_na, _strip_accents(_normalize(p)))
        for p in DIAGNOSIS_REQUEST_PATTERNS
    )


def needs_human_handoff(text: str) -> bool:
    """Phát hiện yêu cầu gặp người thật / tình huống nhạy cảm (bắt cả câu không dấu)."""
    norm_na = _strip_accents(_normalize(text))
    return any(
        _contains_word(norm_na, _strip_accents(_normalize(t)))
        for t in HANDOFF_PATTERNS
    )


def add_disclaimer(reply: str) -> str:
    """Gắn disclaimer vào cuối câu trả lời tư vấn khoa."""
    return reply + DISCLAIMER


# ---------------------------------------------------------------------------
# 4) AUDIT LOG  -> ghi lại hội thoại (đã ẩn PII) để truy vết & tuân thủ.
# ---------------------------------------------------------------------------
def _rotate_audit_log_if_needed():
    """Phải gọi trong lúc giữ _AUDIT_LOCK (xem audit())."""
    try:
        if (os.path.exists(AUDIT_LOG_PATH)
                and os.path.getsize(AUDIT_LOG_PATH) >= AUDIT_LOG_MAX_BYTES):
            rotated_path = AUDIT_LOG_PATH + ".1"
            os.replace(AUDIT_LOG_PATH, rotated_path)  # ghi đè .1 cũ nếu có
    except OSError:
        pass  # rotation lỗi không được chặn ghi log mới


def audit(session_id: str, role: str, message: str, meta: dict | None = None):
    """Ghi một dòng log JSON cho mỗi lượt hội thoại (UTC, tự xoay vòng, fail-safe)."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session": session_id,
        "role": role,
        "message": mask_pii(message),  # luôn ẩn PII trước khi lưu
        "meta": meta or {},
    }
    try:
        with _AUDIT_LOCK:
            _rotate_audit_log_if_needed()
            with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # log lỗi (bất kỳ loại nào, kể cả TypeError từ json.dumps trên meta
              # không serialize được) không được làm gián đoạn hội thoại.
