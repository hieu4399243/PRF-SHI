"""
Triage engine — phần "hàm lượng AI" của đề tài (phòng khám Nha khoa SHI).

Nhiệm vụ: nhận mô tả triệu chứng răng miệng bằng tiếng Việt -> phân loại đúng
NHÓM DỊCH VỤ nha khoa (sâu răng, nội nha, nha chu, chỉnh nha...).

Cách tiếp cận là *rule-based scoring* (chấm điểm theo từ khóa) để chạy được
ngay không cần API key. Có HAI phiên bản để phục vụ ĐÁNH GIÁ/so sánh:

  - v1: so khớp từ khóa trên văn bản đã viết thường (bản gốc).
  - v2: như v1 nhưng so khớp KHÔNG phân biệt dấu (accent-insensitive),
        bắt được cả khi người dùng gõ thiếu dấu — rất phổ biến ở tiếng Việt.

Cấu trúc tách rời nên có thể thay `classify_symptoms()` bằng một lời gọi LLM
(vd. Claude) mà không đụng phần còn lại. Xem hàm classify_with_llm() ở cuối.
"""

import re
import unicodedata
from data import DEPARTMENTS

DEFAULT_VERSION = "v2"  # phiên bản dùng trong sản phẩm (chatbot)

# Ký tự KHÔNG phải chữ/số -> coi như khoảng trắng (tách từ, bỏ dấu câu).
_NON_WORD = re.compile(r"[^0-9a-zA-ZÀ-ỹà-ỹ]+", re.UNICODE)


def _normalize(text: str) -> str:
    """Chuẩn hóa: viết thường, đổi dấu câu thành khoảng trắng, gộp khoảng trắng."""
    return " ".join(_NON_WORD.sub(" ", text.lower()).split())


def _strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt: 'răng sâu' -> 'rang sau' (giữ chữ 'đ' -> 'd')."""
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def _contains_word(haystack: str, needle: str) -> bool:
    """Khớp theo RANH GIỚI TỪ (whole-word), tránh 'chân răng' chứa 'hàn răng'.

    Cả hai chuỗi đã được chuẩn hóa (token cách nhau bởi 1 khoảng trắng).
    """
    return f" {needle} " in f" {haystack} "


def classify_symptoms(text: str, version: str = DEFAULT_VERSION):
    """Phân loại triệu chứng -> danh sách dịch vụ kèm điểm số, giảm dần.

    Trả về list các dict: [{code, name, desc, score, matched: [...]}, ...]

    version='v1': so khớp từ khóa có dấu.
    version='v2': so khớp không phân biệt dấu (bắt cả văn bản gõ thiếu dấu).
    """
    norm = _normalize(text)
    norm_na = _strip_accents(norm)  # bản không dấu, dùng cho v2
    results = []

    for code, dept in DEPARTMENTS.items():
        score = 0
        matched = []
        for kw in dept["keywords"]:
            hit = _contains_word(norm, kw)
            if not hit and version == "v2":
                hit = _contains_word(norm_na, _strip_accents(kw))
            if hit:
                # từ khóa dài (cụm) có trọng số cao hơn từ đơn
                weight = 2 if " " in kw else 1
                score += weight
                matched.append(kw)
        if score > 0:
            results.append({
                "code": code,
                "name": dept["name"],
                "desc": dept["desc"],
                "score": score,
                "matched": matched,
            })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def best_department(text: str, version: str = DEFAULT_VERSION):
    """Trả về dịch vụ phù hợp nhất, hoặc None nếu không nhận diện được."""
    results = classify_symptoms(text, version=version)
    return results[0] if results else None


def confidence_level(results) -> str:
    """Ước lượng độ tin cậy để quyết định có cần hỏi thêm hay không.

    - 'high'   : có dịch vụ dẫn đầu rõ ràng.
    - 'medium' : nhận ra dịch vụ nhưng điểm sát nhau (cần xác nhận).
    - 'low'    : không nhận ra triệu chứng nào.
    """
    if not results:
        return "low"
    if len(results) == 1:
        return "high"
    top, second = results[0]["score"], results[1]["score"]
    if top >= second + 2:
        return "high"
    return "medium"


# Câu hỏi follow-up có cấu trúc khi độ tin cậy thấp/trung bình.
FOLLOWUP_QUESTIONS = [
    "Bạn đang khó chịu ở vùng răng/nướu nào, và cảm giác chính là gì (đau, ê buốt, chảy máu...)?",
    "Tình trạng này kéo dài bao lâu rồi (vài giờ, vài ngày, hay lâu hơn)?",
    "Có kèm sưng, sốt, hay đau tăng khi ăn nóng/lạnh/ngọt không?",
]


# ---------------------------------------------------------------------------
# ĐIỂM TÍCH HỢP LLM (tùy chọn) — để nâng cấp NLU tiếng Việt.
# Mặc định KHÔNG bật để dự án chạy được ngay. Khi cần độ chính xác cao hơn,
# có thể gọi Claude API tại đây và trả về cùng định dạng như classify_symptoms.
# ---------------------------------------------------------------------------
def classify_with_llm(text: str):  # pragma: no cover - placeholder tích hợp
    """Khung tích hợp Claude (claude-opus-4-8 / claude-sonnet-4-6).

    Gợi ý triển khai:
        from anthropic import Anthropic
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        # prompt yêu cầu model chọn 1 trong các mã dịch vụ trong DEPARTMENTS,
        # KHÔNG chẩn đoán, KHÔNG kê đơn; trả JSON {code, confidence}.
    Hiện trả về None để hệ thống fallback sang rule-based.
    """
    return None
