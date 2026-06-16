"""
Triage engine — phần "hàm lượng AI" của đề tài.

Nhiệm vụ: nhận mô tả triệu chứng bằng tiếng Việt -> phân loại đúng chuyên khoa.

Cách tiếp cận ở đây là *rule-based scoring* (chấm điểm theo từ khóa) để chạy
được ngay không cần API key. Cấu trúc đã tách rời nên có thể thay
`classify_symptoms()` bằng một lời gọi LLM (vd. Claude) mà không đụng phần còn
lại của hệ thống. Xem hàm classify_with_llm() ở cuối để biết điểm tích hợp.
"""

import unicodedata
from data import DEPARTMENTS


def _normalize(text: str) -> str:
    """Chuẩn hóa: viết thường, bỏ khoảng trắng thừa."""
    return " ".join(text.lower().split())


def classify_symptoms(text: str):
    """Phân loại triệu chứng -> danh sách khoa kèm điểm số, sắp xếp giảm dần.

    Trả về list các dict: [{code, name, desc, score, matched: [...]}, ...]
    """
    norm = _normalize(text)
    results = []

    for code, dept in DEPARTMENTS.items():
        score = 0
        matched = []
        for kw in dept["keywords"]:
            if kw in norm:
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


def best_department(text: str):
    """Trả về khoa phù hợp nhất, hoặc None nếu không nhận diện được."""
    results = classify_symptoms(text)
    return results[0] if results else None


def confidence_level(results) -> str:
    """Ước lượng độ tin cậy để quyết định có cần hỏi thêm hay không.

    - 'high'   : có khoa dẫn đầu rõ ràng.
    - 'medium' : nhận ra khoa nhưng điểm sát nhau (cần xác nhận).
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
    "Triệu chứng chính khiến bạn khó chịu nhất là gì?",
    "Bạn bị tình trạng này bao lâu rồi (vài giờ, vài ngày, hay lâu hơn)?",
    "Triệu chứng có kèm sốt, đau, hay khó thở không?",
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
        # prompt yêu cầu model chọn 1 trong các mã khoa trong DEPARTMENTS,
        # KHÔNG chẩn đoán, KHÔNG kê đơn; trả JSON {code, confidence}.
    Hiện trả về None để hệ thống fallback sang rule-based.
    """
    return None
