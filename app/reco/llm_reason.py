"""
LLM viết lại câu lý do gợi ý cho tự nhiên hơn — bật mặc định (`REC_LLM_REASON`).

⚠️ SAI LỆCH CÓ CHỦ ĐÍCH so với spec: SEQ bước 5.3 nói `reason_text` sinh từ
template. Đây là quyết định của chủ dự án, xem §3 (D1) doc thiết kế.

RÀNG BUỘC BẤT BIẾN — đây là điều làm cho sai lệch trên vẫn an toàn:

    LLM CHỈ ĐƯỢC ĐỔI CÂU CHỮ.

Nó không thấy và không đổi được `service_code`, `confidence`, `rank`, `urgency`.
Thứ hạng gợi ý luôn do bộ luật thuần sinh ra (reco/rules.py), nên:
  - kết quả tái lập được -> eval chấm lại ra đúng con số cũ;
  - một lỗi/ảo giác của LLM không bao giờ đổi được NỘI DUNG gợi ý y tế, chỉ làm
    câu giải thích quay về template.

Cache khoá theo CHÍNH CÂU TEMPLATE (không theo bệnh nhân): câu template đã chứa
đủ mọi con số cần thiết, không chứa thông tin định danh, và tập câu là hữu hạn
(số reason_code × số dịch vụ) nên tỉ lệ cache hit rất cao. Đây là cách giữ SLA
khi bật LLM — xem §9.3 doc thiết kế.
"""

import os
import re
import threading

# Import chéo sang `triage/` (vi phạm quy tắc "module nghiệp vụ không import lẫn
# nhau" ở docs/code-standards.md). Chấp nhận có ý thức: `triage/llm.py` là CỔNG RA
# DUY NHẤT tới mô hình ngôn ngữ của cả dự án, và `triage/safety.py` giữ bộ chặn nội
# dung. Cách sạch hơn là chuyển hai module đó xuống `core/`, nhưng
# tests/test_triage_llm.py đang monkeypatch trực tiếp `app.triage.llm` nên việc di
# chuyển sẽ làm hỏng khả năng mock ở đó -> để lại thành việc riêng (D6 trong doc).
from ..triage import llm, safety
from . import reasons

MAX_TOKENS = 700

# Viết văn bản chứ không phân loại -> temperature 0 làm câu rập khuôn, 4 gợi ý ra
# gần như cùng một khuôn mẫu. Nâng vừa phải cho tự nhiên hơn. An toàn vì `reason_text`
# KHÔNG tham gia xếp hạng: kết quả gợi ý vẫn tái lập được, chỉ câu chữ khác đi.
TEMPERATURE = 0.45

_cache = {}
_CACHE_MAX = 512
_CACHE_LOCK = threading.Lock()

# SĐT Việt Nam trong câu lý do = dấu hiệu LLM bịa hoặc rò dữ liệu -> loại.
_PHONE_RE = re.compile(r"\b0\d{8,10}\b")

_SYSTEM_PROMPT = (
    "Bạn viết lại câu giải thích gợi ý dịch vụ cho một PHÒNG KHÁM NHA KHOA Việt Nam.\n\n"
    "Mỗi dòng đầu vào có dạng:  <số thứ tự>. [tên dịch vụ] <câu gốc>\n"
    "Viết lại CÂU GỐC thành MỘT câu tiếng Việt tự nhiên, thân thiện, giữ NGUYÊN ý "
    "nghĩa và mọi con số.\n\n"
    "QUY TẮC BẮT BUỘC:\n"
    "1. Không chẩn đoán bệnh, không nêu tên bệnh, không kê thuốc.\n"
    "2. Không hứa hiệu quả điều trị, không gây lo sợ.\n"
    "3. Không dùng thuật ngữ kỹ thuật (AI, thuật toán, điểm số, mô hình...).\n"
    "4. Không thêm số liệu mới, không thêm tên người, không thêm số điện thoại.\n"
    "5. Tên dịch vụ trong [] CHỈ LÀ NGỮ CẢNH để bạn hiểu đang nói về dịch vụ nào. "
    "TUYỆT ĐỐI không nhắc tên một dịch vụ nha khoa nào khác trong câu; nếu cần thì "
    'gọi là "dịch vụ này".\n'
    "6. Giữ đúng ý nghĩa mốc thời gian. \"nên làm lại MỖI 3 tháng\" (chu kỳ lặp) "
    'KHÁC "hẹn lại SAU 3 tháng nữa" (một mốc trong tương lai) — không được đổi.\n'
    "7. Tối đa 100 ký tự mỗi câu.\n\n"
    "VÍ DỤ (học phong cách, đừng chép lại nội dung):\n"
    "  vào : 0. [Khám tổng quát & Cạo vôi] Đã 7 tháng kể từ lần khám tổng quát & "
    "cạo vôi gần nhất — đã tới hạn kiểm tra lại.\n"
    "  ra  : Đã 7 tháng kể từ lần kiểm tra gần nhất, bạn nên ghé lại để cạo vôi nhé.\n"
    "  vào : 1. [Nha khoa thẩm mỹ] Bạn từng dùng dịch vụ này 2 năm trước; dịch vụ "
    "này nên làm lại mỗi khoảng 12 tháng.\n"
    "  ra  : Bạn từng làm cách đây 2 năm, trong khi dịch vụ này nên lặp lại mỗi 12 tháng.\n"
    "  vào : 2. [Trám răng / Sâu răng] 43% bệnh nhân từng khám tổng quát & cạo vôi "
    "cũng đã dùng dịch vụ này.\n"
    "  ra  : 43% bệnh nhân có lịch khám giống bạn cũng đã chọn dịch vụ này.\n\n"
    'CHỈ trả JSON: {"reasons": [{"i": <số thứ tự>, "text": "<câu mới>"}]}'
)


def is_enabled():
    """LLM viết lý do có bật không? Mặc định BẬT nếu có API key."""
    flag = (os.environ.get("REC_LLM_REASON") or "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    return llm.is_enabled()


def _cache_get(key):
    with _CACHE_LOCK:
        return _cache.get(key)


def _cache_put(key, value):
    with _CACHE_LOCK:
        if len(_cache) >= _CACHE_MAX:
            _cache.clear()  # cache demo: đầy thì xoá sạch, đủ dùng
        _cache[key] = value


def clear_cache():
    with _CACHE_LOCK:
        _cache.clear()


def _acceptable(text, original):
    """Câu LLM có dùng được không? 4 lớp kiểm duyệt (§9.2 doc thiết kế)."""
    if not text or not isinstance(text, str):
        return False
    text = text.strip()
    if not text or len(text) > reasons.MAX_REASON_LENGTH:
        return False
    if reasons.has_banned_term(text):
        return False
    # Khẳng định về bệnh/thuốc/kết quả điều trị -> loại (bộ chặn riêng cho ĐẦU RA).
    if reasons.has_medical_claim(text):
        return False
    # Thêm bộ chặn câu HỎI chẩn đoán của dự án: rẻ, và bắt được dạng LLM viết lại
    # thành câu hỏi ("Bạn có bị sao không?").
    if safety.is_diagnosis_request(text):
        return False
    if _PHONE_RE.search(text):
        return False
    # Câu rỗng nghĩa: chỉ lặp lại nguyên văn thì giữ template cho nhất quán.
    if text == original.strip():
        return False
    return True


def _names_other_service(text, item):
    """Câu viết lại có nhắc tên một dịch vụ KHÁC dịch vụ đang giải thích không?

    Lỗi quan sát được trên dữ liệu thật: gợi ý "Nha chu" bị LLM viết thành "bạn nên
    kiểm tra răng định kỳ" — tức nói về "Khám tổng quát". Bệnh nhân đọc card sẽ thấy
    tiêu đề một dịch vụ mà lý do nói về dịch vụ khác.

    So khớp theo TỪ KHOÁ ĐẶC TRƯNG của từng dịch vụ (không phân biệt dấu): chỉ nhận
    từ khoá dài >= 2 từ để "răng", "nướu" không tự làm mọi câu bị loại.

    Miễn trừ các dịch vụ mà CHÍNH tín hiệu đang giải thích tham chiếu tới: lý do
    `care_pathway` và `similar_patients` buộc phải nhắc dịch vụ trước đó ("Sau khi
    nội nha, bước tiếp theo..."). Không miễn trừ thì hai luật này luôn bị loại oan.
    """
    from ..core.catalog import DEPARTMENTS
    from ..core.text import normalize, strip_accents

    allowed = {item.get("service_code")}
    for signal in item.get("signals") or []:
        referenced = (signal.get("ctx") or {}).get("from_service")
        if referenced:
            allowed.add(referenced)

    low = strip_accents(normalize(text or ""))
    for code, dept in DEPARTMENTS.items():
        if code in allowed:
            continue
        for phrase in [dept.get("name", "")] + list(dept.get("keywords", [])):
            needle = strip_accents(normalize(phrase))
            if len(needle.split()) >= 2 and needle in low:
                return True
    return False


def polish(items):
    """Viết lại `reason_text` của từng gợi ý. Trả về CHÍNH list `items` đã cập nhật.

    Không bao giờ raise. Mọi sự cố (LLM tắt, timeout, JSON hỏng, câu vi phạm) đều
    dẫn tới việc giữ nguyên `reason_text` template của mục đó.
    """
    if not items or not is_enabled():
        return items

    # Chỉ hỏi LLM những câu chưa có trong cache. Khoá cache gồm cả `service_code`:
    # hai dịch vụ khác nhau có thể sinh ra CÙNG câu template (vd. cùng số tháng),
    # mà câu đã viết lại thì gắn với ngữ cảnh dịch vụ -> dùng chung sẽ nói sai dịch vụ.
    pending = []
    for item in items:
        template = item.get("reason_text") or ""
        cached = _cache_get((item.get("service_code"), template))
        if cached:
            item["reason_text"] = cached
            item["reason_source"] = "llm-cache"
        elif template:
            pending.append(item)

    if not pending:
        return items

    # Kèm tên dịch vụ làm ngữ cảnh: template dùng cụm "dịch vụ này" nên nếu không
    # nói rõ, LLM không biết đang giải thích dịch vụ nào và sẽ TỰ BỊA một tên khác
    # (quan sát thực tế: "Nha chu" bị viết lại thành "kiểm tra răng định kỳ").
    numbered = "\n".join(f'{i}. [{item.get("name") or item.get("service_code")}] '
                         f'{item["reason_text"]}'
                         for i, item in enumerate(pending))
    payload = llm.chat_json(_SYSTEM_PROMPT, numbered, max_tokens=MAX_TOKENS,
                            temperature=TEMPERATURE)
    if not isinstance(payload, dict):
        return items  # LLM lỗi -> toàn bộ giữ template

    by_index = {}
    for entry in payload.get("reasons") or []:
        if isinstance(entry, dict):
            try:
                by_index[int(entry.get("i"))] = entry.get("text")
            except (TypeError, ValueError):
                continue

    for i, item in enumerate(pending):
        original = item["reason_text"]
        candidate = by_index.get(i)
        if _acceptable(candidate, original) and not _names_other_service(candidate, item):
            text = candidate.strip()
            item["reason_text"] = text
            item["reason_source"] = "llm"
            _cache_put((item.get("service_code"), original), text)
        else:
            item["reason_source"] = "template"

    return items
