"""
LLM viết câu trả lời cho các NHÁNH FALLBACK của hội thoại — bật mặc định
(`CHAT_LLM_REPLY`).

Vì sao cần: LLM trong dự án này mới chỉ làm việc PHÂN LOẠI (triage/engine.py trả
về một mã dịch vụ), còn mọi câu chữ bệnh nhân đọc đều là template cứng trong
`steps/`. Nên khi người dùng nói một câu mà bộ luật không có nhánh nào khớp
("bạn có chắc không?", "tôi ăn cơm thấy không ngon"), bot chỉ biết lặp lại
"vui lòng chọn một dịch vụ ở các nút bên trên" — đúng luật nhưng vô cảm, và
người dùng cảm giác đang nói chuyện với cây quyết định.

RÀNG BUỘC BẤT BIẾN (giống hệt `reco/llm_reason.py`):

    LLM CHỈ ĐƯỢC ĐỔI CÂU CHỮ.

Nó không nhìn thấy và không đổi được `state` lẫn `options` — hai thứ đó do máy
trạng thái quyết định XONG rồi mới gọi tới đây. Hệ quả: LLM lỗi/timeout/bịa đặt
thì cùng lắm là quay về đúng câu template cũ, KHÔNG bao giờ làm hội thoại nhảy
sai bước hay mất nút bấm.

CHỖ CỐ Ý KHÔNG BAO GIỜ GỌI LLM (giữ 100% tất định):
  - guardrail cấp cứu / chuyển người thật / chặn chẩn đoán: router.py chặn TRƯỚC
    khi tới bước, và ở TRIAGE thì `do_triage()` tự chặn inline;
  - PICK_DATE / PICK_TIME: câu trả lời ở đó phải nêu ĐÚNG ngày–giờ còn trống,
    không được để một mô hình sinh văn bản đụng vào (xem `_ALLOWED_STATES`);
  - ASK_NAME / ASK_PHONE: nội dung người dùng gõ ở đó chính là PII.

KHÔNG cache: đầu vào là câu tự do của người dùng nên tỉ lệ trùng gần như 0, mà
cache lại đồng nghĩa với giữ văn bản người dùng trong bộ nhớ lâu hơn mức cần.
"""

import os
import re

# Import chéo sang `triage/` — cùng lý do (và cùng mức chấp nhận có ý thức) đã
# ghi ở đầu `reco/llm_reason.py`: `triage/llm.py` là CỔNG RA DUY NHẤT tới mô hình
# ngôn ngữ, `triage/safety.py` giữ bộ chặn nội dung. `chatbot/` vốn được phép
# điều phối các module nghiệp vụ nên ở đây không phá quy tắc biên module.
from ..core.catalog import DEPARTMENTS
from ..triage import llm, safety

MAX_TOKENS = 400

# Sinh văn bản chứ không phân loại -> temperature 0 làm câu rập khuôn, hỏi 3 lần
# ra 3 câu y hệt. Nâng vừa phải cho tự nhiên. An toàn vì câu chữ KHÔNG tham gia
# vào quyết định bước tiếp theo.
TEMPERATURE = 0.5

# Dài hơn ngần này là LLM đang viết luận, không phải trả lời trong khung chat.
MAX_REPLY_LENGTH = 420

# Chỉ những bước KHÔNG đụng tới dữ liệu lịch/PII mới được viết lại (xem docstring).
_ALLOWED_STATES = {"TRIAGE", "CONFIRM_DEPT", "PICK_DOCTOR"}

# --- Bộ kiểm duyệt ĐẦU RA ---------------------------------------------------
# Nguyên tắc: thà loại oan một câu hay rồi quay về template, còn hơn để một câu
# chẩn đoán / một con số bịa tới bệnh nhân.

# Khẳng định về bệnh tật, thuốc men, kết quả điều trị = chẩn đoán.
# Cố ý KHÔNG chặn trần trụi "viêm"/"áp xe": mô tả dịch vụ trong danh mục có sẵn
# hai từ đó ("Viêm tủy, đau răng dữ dội, áp xe răng"), mà câu nguy hiểm thật sự
# là câu GẮN nó vào người bệnh — dạng đó đã bị "bạn bị"/"bạn đang bị" bắt.
_MEDICAL_CLAIM_TERMS = (
    "bạn bị", "bạn đang bị", "bạn có bệnh", "bạn mắc", "chẩn đoán là",
    "chắc chắn là bạn", "thuốc", "kháng sinh", "kê đơn", "liều",
    "khỏi hẳn", "chữa khỏi", "đảm bảo khỏi", "cam kết",
)

# Lộ chuyện kỹ thuật -> phá vỡ vai "trợ lý phòng khám".
# "mô hình" là từ có thật trong nha khoa (mẫu hàm), nhưng ở 3 bước fallback này
# thì không có lý do gì để nhắc tới -> chặn luôn, loại oan thì quay về template.
_TECH_TERMS = re.compile(
    r"\b(ai|llm|api|model|prompt|token)\b|thuật toán|mô hình|điểm số|chấm điểm|"
    r"hệ thống của (tôi|mình)", re.IGNORECASE)

# Số điện thoại: LLM bịa hotline hoặc lặp lại SĐT người dùng vừa gõ.
_PHONE_RE = re.compile(r"\b0\d{8,10}\b")

# Bảng giá KHÔNG nằm trong ngữ cảnh gửi cho LLM -> mọi con số tiền đều là bịa.
_PRICE_RE = re.compile(r"\d[\d.,]*\s*(k|nghìn|ngàn|triệu|đồng|đ|vnđ|vnd)\b",
                       re.IGNORECASE)

# Ngày/giờ cũng vậy: lịch trống do booking/ quyết định, các bước được phép viết
# lại ở đây đều CHƯA biết lịch, nên nhắc tới một mốc cụ thể là hứa suông.
_SCHEDULE_RE = re.compile(r"\b\d{1,2}\s*(h|giờ)\b|\b\d{1,2}:\d{2}\b|\b\d{1,2}/\d{1,2}\b",
                          re.IGNORECASE)

# Chat bubble chỉ render được vài thẻ này (xem templates/). Thẻ lạ -> loại.
_BAD_TAG_RE = re.compile(r"<(?!/?(?:b|i|br)\s*/?>)", re.IGNORECASE)

_TAG_RE = re.compile(r"<[^>]+>")

_SYSTEM_PROMPT = (
    "Bạn là trợ lý ảo của một PHÒNG KHÁM NHA KHOA Việt Nam. Nhiệm vụ duy nhất "
    "của bạn: giúp bệnh nhân chọn đúng dịch vụ nha khoa và đặt lịch hẹn.\n\n"
    "Bộ luật của hệ thống đã KHÔNG hiểu câu vừa rồi của bệnh nhân và định đọc một "
    "câu mặc định cứng nhắc. Việc của bạn là viết một câu trả lời TỰ NHIÊN thay "
    "cho câu mặc định đó: trả lời đúng điều bệnh nhân vừa hỏi, rồi dẫn họ tiếp "
    "tục đúng bước hiện tại.\n\n"
    "QUY TẮC BẮT BUỘC:\n"
    "1. CHỈ dùng dữ kiện được cung cấp bên dưới. Tuyệt đối không bịa tên dịch vụ, "
    "tên bác sĩ, giá tiền, ngày, giờ, số điện thoại, địa chỉ.\n"
    "2. Không chẩn đoán bệnh, không khẳng định bệnh nhân đang bị bệnh gì, không "
    "nhắc tên thuốc, không hứa chữa khỏi. Nếu bị hỏi bệnh gì / có nặng không, hãy "
    "nói thẳng là bạn chỉ giúp chọn dịch vụ, nha sĩ khám trực tiếp mới kết luận được.\n"
    "3. Nếu bệnh nhân hỏi \"có chắc không\", \"sao lại là dịch vụ này\": giải thích "
    "ngắn gọn rằng bạn ghép theo MÔ TẢ họ vừa kể với phạm vi của dịch vụ đó, và "
    "đây là gợi ý chứ không phải kết luận y khoa.\n"
    "4. Nếu bệnh nhân nói chuyện ngoài chủ đề răng miệng: đáp lại một câu ngắn cho "
    "lịch sự rồi kéo về việc chọn dịch vụ / đặt lịch. Không tiếp chuyện phiếm dài.\n"
    "5. Giữ nguyên Ý của câu mặc định (nó cho biết bệnh nhân cần làm gì tiếp) — "
    "bạn chỉ đổi cách nói cho tự nhiên, và trả lời thêm câu hỏi của họ.\n"
    "6. Không nhắc tới AI, mô hình, thuật toán, hệ thống, nút bấm không tồn tại.\n"
    "7. Xưng \"mình\", gọi \"bạn\". Tối đa 3 câu, dưới 300 ký tự. Thân thiện, "
    "không nhõng nhẽo, không dùng emoji.\n"
    "8. Chỉ được dùng thẻ HTML <b>, <i>, <br>. Không markdown, không danh sách.\n\n"
    # Ví dụ cố ý CHỌN TÌNH HUỐNG KHÁC với các ca đã biết hỏng (\"bạn có chắc không\",
    # \"ăn cơm không ngon\"). Đặt đúng câu đó vào đây thì model chép lại gần nguyên
    # văn — nhìn thì hay nhưng là khớp mẫu, không phải hiểu.
    "VÍ DỤ (học PHONG CÁCH, đừng chép nội dung):\n"
    "  Bệnh nhân: \"sao lại là dịch vụ này, tôi thấy có mỗi tí thôi mà\"  "
    "(đang đề xuất Nha chu)\n"
    "  Trả lời  : \"Mình ghép <b>Nha chu</b> theo mô tả bạn vừa kể, vì phần nướu "
    "thuộc phạm vi dịch vụ này. Đây là gợi ý để bạn đi khám cho đúng chỗ thôi, nặng "
    "nhẹ ra sao thì nha sĩ xem trực tiếp mới nói được. Bạn muốn đặt lịch không?\"\n"
    "  Bệnh nhân: \"tối qua tôi ngủ không được\"\n"
    "  Trả lời  : \"Nếu răng miệng đang làm bạn mất ngủ thì nên xử lý sớm đó. Bạn tả "
    "giúp mình rõ hơn nhé: khó chịu ở chỗ nào, và là đau, ê buốt hay sưng?\"\n"
    "  Bệnh nhân: \"phòng khám có xa trung tâm không\"\n"
    "  Trả lời  : \"Phần địa chỉ bạn hỏi lễ tân giúp mình nhé, mình chỉ hỗ trợ chọn "
    "dịch vụ và đặt lịch thôi. Quay lại việc chính, bạn muốn chọn dịch vụ nào?\"\n\n"
    "CHỈ trả JSON: {\"reply\": \"<câu trả lời>\"}"
)


def is_enabled() -> bool:
    """LLM viết câu trả lời có bật không? Mặc định BẬT nếu có API key."""
    flag = (os.environ.get("CHAT_LLM_REPLY") or "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    return llm.is_enabled()


def _plain(html: str) -> str:
    """Bỏ thẻ HTML để câu template vào prompt cho gọn (LLM không cần thấy markup)."""
    return " ".join(_TAG_RE.sub(" ", html or "").split())


def _context(sess, message, state, template, facts):
    """Dựng khối DỮ KIỆN gửi kèm — LLM chỉ được nói dựa trên đúng những dòng này."""
    lines = [f"BƯỚC HIỆN TẠI: {state}"]

    dept = DEPARTMENTS.get(sess.get("dept_code"))
    if dept:
        lines.append(f"DỊCH VỤ ĐANG CHỌN: {dept['name']} — {dept['desc']}")

    candidates = [r.get("name") for r in (sess.get("candidates") or [])[:3] if r.get("name")]
    if candidates:
        lines.append("DỊCH VỤ ỨNG VIÊN ĐANG HIỂN THỊ: " + ", ".join(candidates))

    for label, value in (facts or {}).items():
        if value:
            lines.append(f"{label}: {value}")

    # Lượt trước của CHÍNH người dùng: câu hiện tại thường tham chiếu ngược
    # ("bạn có chắc không" — chắc về cái gì?). Chỉ lấy phía người dùng, xem
    # ghi chú ở session.new_session().
    earlier = (sess.get("user_turns") or [])[:-1]
    if earlier:
        lines.append("BỆNH NHÂN ĐÃ NÓI TRƯỚC ĐÓ: " + " / ".join(earlier))

    lines.append("CÂU MẶC ĐỊNH CỦA HỆ THỐNG (ý bắt buộc phải giữ): " + _plain(template))
    lines.append("BỆNH NHÂN VỪA NÓI: " + safety.mask_pii(message))
    return "\n".join(lines)


def _acceptable(text, template) -> bool:
    """Câu LLM có được phép gửi tới bệnh nhân không? Sai một điều kiện -> template."""
    if not text or not isinstance(text, str):
        return False
    text = text.strip()
    if not text or len(text) > MAX_REPLY_LENGTH:
        return False
    if text == _plain(template):
        return False  # chép lại y nguyên -> giữ template cho nhất quán
    low = text.lower()
    if any(term in low for term in _MEDICAL_CLAIM_TERMS):
        return False
    if _TECH_TERMS.search(text) or _BAD_TAG_RE.search(text):
        return False
    if _PHONE_RE.search(text) or _PRICE_RE.search(text) or _SCHEDULE_RE.search(text):
        return False
    # Bộ chặn câu HỎI chẩn đoán của dự án: rẻ, và bắt được dạng LLM lỡ viết
    # thành câu hỏi kiểu "bạn có bị sưng không, có nguy hiểm không".
    if safety.is_diagnosis_request(text):
        return False
    return True


def soften(sess, message, state, template, facts=None):
    """Viết lại `template` cho tự nhiên và trả lời đúng câu người dùng vừa hỏi.

    Không bao giờ raise. Mọi sự cố (LLM tắt, timeout, JSON hỏng, câu vi phạm bộ
    kiểm duyệt) đều trả về CHÍNH `template` — tức hội thoại lùi về đúng hành vi
    rule-based cũ.

    Args:
        sess: session dict (đọc dept_code, candidates, user_turns — không ghi).
        message: câu người dùng vừa gõ.
        state: bước hiện tại, phải nằm trong `_ALLOWED_STATES`.
        template: câu mặc định của bước (HTML), cũng là fallback.
        facts: dict {nhãn: giá trị} dữ kiện thêm của bước, vd. danh sách bác sĩ.

    Returns:
        Chuỗi HTML để đưa vào `reply()`.
    """
    if not is_enabled() or state not in _ALLOWED_STATES:
        return template
    message = (message or "").strip()
    if not message:
        return template
    # Phòng thủ nhiều lớp: router đã chặn cấp cứu/handoff trước khi tới bước, còn
    # yêu cầu chẩn đoán thì template đã chứa sẵn câu từ chối chuẩn — không giao
    # cho LLM diễn đạt lại lời từ chối.
    if safety.check_emergency(message) or safety.is_diagnosis_request(message):
        return template

    payload = llm.chat_json(_SYSTEM_PROMPT,
                            _context(sess, message, state, template, facts),
                            max_tokens=MAX_TOKENS, temperature=TEMPERATURE)
    if not isinstance(payload, dict):
        return template
    candidate = payload.get("reply")
    if not _acceptable(candidate, template):
        return template
    text = candidate.strip()

    # Ở CONFIRM_DEPT, câu người dùng hỏi hầu như luôn là "sao lại là dịch vụ này?"
    # -> câu trả lời TÁI KHẲNG ĐỊNH một gợi ý dịch vụ. Mọi câu như vậy trong dự án
    # đều phải đeo disclaimer (xem safety.add_disclaimer ở do_triage/describe_service),
    # và không giao việc đó cho LLM nhớ hộ.
    if state == "CONFIRM_DEPT" and sess.get("dept_code"):
        text = safety.add_disclaimer(text)
    return text
