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

from ..core.text import contains_word, normalize, strip_accents

from ..core.paths import AUDIT_LOG_PATH
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
#
# Nguyên tắc khi thêm: liệt kê MỌI CÁCH GỌI CON NGƯỜI ở phòng khám, trừ
# "bác sĩ"/"nha sĩ" — hai từ đó ở đây nghĩa là muốn ĐI KHÁM, tức luồng đặt lịch
# bình thường (xem chatbot/llm_reply.py::_is_booking_not_escalation).
#
# Bài học từ lỗi thật: bản đầu chỉ có 7 mục nên "tôi cần gặp y tá" rơi tọt qua cả
# lớp từ khoá lẫn lớp LLM, và bot trả lời "mình không có chức năng hẹn gặp y tá"
# — đúng chữ nhưng sai hẳn nghiệp vụ, vì AC là "yêu cầu gặp nhân viên BẤT CỨ LÚC
# NÀO". Danh sách này cố ý RỘNG: nhận nhầm thì cùng lắm chuyển sang người thật,
# còn bỏ sót thì bệnh nhân bị bỏ rơi.
_SEED_HANDOFF_PATTERNS = [
    # Cách gọi người hỗ trợ
    "gặp người", "nhân viên", "tư vấn viên", "y tá", "điều dưỡng", "lễ tân",
    "trợ lý", "quản lý", "người phụ trách", "người hỗ trợ", "tổng đài",
    "chăm sóc khách hàng", "người thật", "người trực",
    # Cách diễn đạt ý muốn thoát khỏi bot
    "nói chuyện với người thật", "gọi cho tôi", "gọi lại cho tôi",
    "gặp ai đó", "có ai đó không", "có ai không",
    # Bất mãn -> cũng phải tới người thật
    "khiếu nại", "phàn nàn", "không hài lòng",
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
        from ..core import storage
        if storage.USE_DB:
            db = storage.list_safety_patterns() or {}
    except Exception as exc:
        db = {}  # lỗi DB/mạng -> dùng seed, KHÔNG để guardrail biến mất
        print(f"[safety] CẢNH BÁO: lỗi khi nạp guardrail patterns từ DB, "
              f"dùng seed tĩnh. Lỗi: {exc}")
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
    norm_na = strip_accents(normalize(text))
    return any(
        contains_word(norm_na, strip_accents(normalize(p)))
        for p in EMERGENCY_PATTERNS
    )


def is_diagnosis_request(text: str) -> bool:
    """Người dùng đang yêu cầu chẩn đoán / kê đơn? (bắt cả câu không dấu)"""
    norm_na = strip_accents(normalize(text))
    return any(
        contains_word(norm_na, strip_accents(normalize(p)))
        for p in DIAGNOSIS_REQUEST_PATTERNS
    )


def needs_human_handoff(text: str) -> bool:
    """Phát hiện yêu cầu gặp người thật / tình huống nhạy cảm (bắt cả câu không dấu)."""
    norm_na = strip_accents(normalize(text))
    return any(
        contains_word(norm_na, strip_accents(normalize(t)))
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


def session_transcript(session_id: str, limit: int = 100):
    """Dựng lại hội thoại của MỘT phiên từ audit log, cũ trước mới sau.

    Dùng khi chuyển tiếp sang nhân viên (CB-05): nhân viên phải đọc được toàn bộ
    những gì đã trao đổi. Đọc lại từ audit log thay vì giữ thêm một bản lịch sử
    trong `SESSIONS` vì audit log MỚI là bản ghi đầy đủ (cả hai phía, đã ẩn PII,
    có timestamp) và không mất khi phiên hết TTL.

    Hệ quả phải chấp nhận: transcript đã ẩn PII, nên nhân viên KHÔNG thấy tên/SĐT
    trong đó — hai trường ấy đi riêng trong bản ghi handoff (xem handoff_step).
    Lượt ngoài cùng bên phải là mới nhất; `limit` cắt bớt phần đầu nếu quá dài.

    Trả [] nếu chưa có log (lần chạy đầu) hoặc file hỏng — không bao giờ raise:
    thiếu transcript không được phép làm hỏng việc chuyển tiếp.
    """
    turns = []
    for path in (AUDIT_LOG_PATH + ".1", AUDIT_LOG_PATH):  # bản xoay vòng trước
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # dòng ghi dở (crash giữa chừng) -> bỏ qua
                    if entry.get("session") == session_id:
                        turns.append({
                            "ts": entry.get("ts"),
                            "role": entry.get("role"),
                            "message": entry.get("message"),
                        })
        except OSError:
            continue
    return turns[-limit:]
