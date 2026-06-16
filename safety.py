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
from datetime import datetime

AUDIT_LOG_PATH = os.path.join(os.path.dirname(__file__), "audit_log.jsonl")

# ---------------------------------------------------------------------------
# 1) PHÁT HIỆN CẤP CỨU  -> hướng dẫn gọi 115, không tư vấn tiếp.
# ---------------------------------------------------------------------------
EMERGENCY_PATTERNS = [
    "đau ngực dữ dội", "đau thắt ngực", "khó thở nặng", "không thở được",
    "ngất", "bất tỉnh", "co giật", "tai biến", "đột quỵ", "méo miệng",
    "liệt nửa người", "chảy máu không cầm", "ho ra máu", "nôn ra máu",
    "tự tử", "muốn chết", "tự làm hại", "khó thở dữ dội", "tím tái",
    "đau ngực lan ra tay", "hôn mê",
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
DIAGNOSIS_REQUEST_PATTERNS = [
    "tôi bị bệnh gì", "bị bệnh gì", "chẩn đoán", "có phải ung thư",
    "uống thuốc gì", "kê đơn", "dùng thuốc gì", "thuốc nào", "liều lượng",
    "có nguy hiểm không", "có sao không", "đơn thuốc",
]

DISCLAIMER = (
    "<br><span class='disclaimer'>ℹ️ Lưu ý: Tôi chỉ hỗ trợ định hướng khoa khám "
    "và đặt lịch, <b>không chẩn đoán bệnh và không kê đơn thuốc</b>. "
    "Chẩn đoán chính xác cần bác sĩ thăm khám trực tiếp.</span>"
)


def check_emergency(text: str) -> bool:
    """Trả về True nếu phát hiện dấu hiệu cấp cứu."""
    low = text.lower()
    return any(p in low for p in EMERGENCY_PATTERNS)


def is_diagnosis_request(text: str) -> bool:
    """Người dùng đang yêu cầu chẩn đoán / kê đơn?"""
    low = text.lower()
    return any(p in low for p in DIAGNOSIS_REQUEST_PATTERNS)


def needs_human_handoff(text: str) -> bool:
    """Phát hiện yêu cầu gặp người thật / tình huống nhạy cảm."""
    low = text.lower()
    triggers = ["gặp người", "nhân viên", "tư vấn viên", "gọi cho tôi",
                "khiếu nại", "không hài lòng", "nói chuyện với người thật"]
    return any(t in low for t in triggers)


def add_disclaimer(reply: str) -> str:
    """Gắn disclaimer vào cuối câu trả lời tư vấn khoa."""
    return reply + DISCLAIMER


# ---------------------------------------------------------------------------
# 4) AUDIT LOG  -> ghi lại hội thoại (đã ẩn PII) để truy vết & tuân thủ.
# ---------------------------------------------------------------------------
def audit(session_id: str, role: str, message: str, meta: dict | None = None):
    """Ghi một dòng log JSON cho mỗi lượt hội thoại."""
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "session": session_id,
        "role": role,
        "message": mask_pii(message),  # luôn ẩn PII trước khi lưu
        "meta": meta or {},
    }
    try:
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # log lỗi không được làm gián đoạn hội thoại
