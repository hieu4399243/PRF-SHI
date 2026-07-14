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
from .data import DEPARTMENTS

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


# ---------------------------------------------------------------------------
# PHỦ ĐỊNH (negation)
# "tôi không bị đau răng" KHÔNG được tính là triệu chứng đau răng. Chỉ nhìn
# NGƯỢC VỀ TRƯỚC từ khóa trong một cửa sổ ngắn, vì trong tiếng Việt "không" đứng
# SAU thường là từ để hỏi, không phải phủ định:
#     "có sâu răng không?"                 -> vẫn là sâu răng (hỏi)
#     "nhức cả đêm không ngủ được"         -> vẫn là nhức răng (không phủ định "nhức")
#     "tôi không bị sâu răng"              -> phủ định
# Gặp liên từ đối lập thì dừng: "không sâu răng nhưng chảy máu chân răng" ->
# "chảy máu chân răng" không bị phủ định lây.
# ---------------------------------------------------------------------------
# Bản CÓ DẤU dùng khi khớp v1; bản KHÔNG DẤU dùng khi khớp v2.
# LƯU Ý: cố ý KHÔNG có "đâu" (phủ định khẩu ngữ) — bỏ dấu xong nó thành "dau",
# trùng với "đau" (triệu chứng) và sẽ tự phủ định chính mình.
_NEG_CUES = {"không", "ko", "k", "chưa", "chẳng", "chả", "hết"}
_NEG_CUES_NA = {"khong", "ko", "k", "chua", "chang", "cha", "het"}
_CONTRAST = {"nhưng", "nhung", "mà", "ma", "còn", "con", "song"}
_NEG_WINDOW = 3  # số token nhìn ngược về trước

# Phủ định KHÔNG được vượt qua ranh giới mệnh đề. _normalize() xoá hết dấu câu,
# nên "có gì bất thường KHÔNG, khám tổng quát" sẽ thành "... khong kham tong quat"
# -> "không" (từ để HỎI, kết thúc mệnh đề trước) đứng sát "khám tổng quát" và bị
# hiểu nhầm thành phủ định nó. Vì vậy khi chấm điểm ta chuẩn hoá bằng
# _normalize_clausal(): dấu câu được thay bằng token mốc _CLAUSE_BREAK, và
# _is_negated() dừng lại ở mốc đó.
_CLAUSE_BREAK = "brk"
_CLAUSE_SEP = re.compile(r"[,.;:!?…\n]+")


def _normalize_clausal(text: str) -> str:
    """Như _normalize() nhưng GIỮ ranh giới mệnh đề dưới dạng token `brk`."""
    parts = (_normalize(p) for p in _CLAUSE_SEP.split(text or ""))
    return f" {_CLAUSE_BREAK} ".join(p for p in parts if p)


def _is_negated(tokens, start: int, accent_free: bool) -> bool:
    """Từ khóa bắt đầu ở tokens[start] có nằm trong tầm phủ định không?"""
    cues = _NEG_CUES_NA if accent_free else _NEG_CUES
    for i in range(start - 1, max(-1, start - 1 - _NEG_WINDOW), -1):
        tok = tokens[i]
        # Hết mệnh đề (dấu phẩy/chấm) hoặc gặp liên từ đối lập -> ngoài tầm phủ định.
        if tok == _CLAUSE_BREAK or tok in _CONTRAST:
            return False
        if tok in cues:
            return True
    return False


def _match_positions(tokens, needle_tokens):
    """Các vị trí (index token) mà `needle_tokens` xuất hiện trọn vẹn trong `tokens`."""
    n = len(needle_tokens)
    if not n:
        return []
    return [i for i in range(len(tokens) - n + 1) if tokens[i:i + n] == needle_tokens]


def _match_kind(haystack: str, needle: str, accent_free: bool) -> str:
    """Phân loại một lần khớp từ khóa: 'none' | 'negated' | 'hit'.

    'negated' = có xuất hiện nhưng MỌI lần xuất hiện đều nằm sau một từ phủ định.
    """
    tokens = haystack.split()
    needle_tokens = needle.split()
    positions = _match_positions(tokens, needle_tokens)
    if not positions:
        return "none"
    if all(_is_negated(tokens, p, accent_free) for p in positions):
        return "negated"
    return "hit"


def classify_symptoms(text: str, version: str = DEFAULT_VERSION):
    """Phân loại triệu chứng -> danh sách dịch vụ kèm điểm số, giảm dần.

    Trả về list các dict: [{code, name, desc, score, matched: [...]}, ...]

    version='v1': so khớp từ khóa có dấu.
    version='v2': so khớp không phân biệt dấu (bắt cả văn bản gõ thiếu dấu).
    """
    results, _ = _score(text, version)
    return results


def _score(text: str, version: str = DEFAULT_VERSION):
    """Chấm điểm thô. Trả (results, negated) — `negated` là các dịch vụ CHỈ khớp
    trong ngữ cảnh phủ định ("tôi không bị đau răng") nên không được tính điểm."""
    norm = _normalize_clausal(text)  # giữ mốc ranh giới mệnh đề cho negation
    norm_na = _strip_accents(norm)  # bản không dấu, dùng cho v2
    results, negated = [], []

    for code, dept in DEPARTMENTS.items():
        score = 0
        matched, matched_neg = [], []
        for kw in dept["keywords"]:
            kind = _match_kind(norm, kw, accent_free=False)
            if kind == "none" and version == "v2":
                kind = _match_kind(norm_na, _strip_accents(kw), accent_free=True)
            if kind == "hit":
                # Cụm càng DÀI càng đặc trưng -> trọng số = số từ trong cụm.
                # ("tẩy trắng răng" = 3 điểm phải thắng "ê buốt" = 2 điểm khi người
                #  dùng hỏi "tẩy trắng xong có ê buốt không".)
                weight = len(kw.split())
                score += weight
                matched.append(kw)
            elif kind == "negated":
                matched_neg.append(kw)

        entry = {"code": code, "name": dept["name"], "desc": dept["desc"]}
        if score > 0:
            results.append({**entry, "score": score, "matched": matched})
        elif matched_neg:
            # Có nhắc tới dịch vụ này, nhưng để PHỦ ĐỊNH nó -> không phải triệu chứng.
            negated.append({**entry, "score": 0, "matched": matched_neg})

    results.sort(key=lambda r: r["score"], reverse=True)
    return results, negated


def negated_matches(text: str, version: str = DEFAULT_VERSION):
    """Các dịch vụ mà người dùng nhắc tới nhưng để PHỦ ĐỊNH ("tôi không bị đau răng").

    Dùng để bot trả lời đúng ý thay vì vẫn gợi ý dịch vụ mà người dùng vừa loại trừ.
    """
    _, negated = _score(text, version)
    return negated


def best_department(text: str, version: str = DEFAULT_VERSION):
    """Trả về dịch vụ phù hợp nhất, hoặc None nếu không nhận diện được."""
    results = classify_symptoms(text, version=version)
    return results[0] if results else None


# Bộ phát hiện "than phiền nha khoa chung": câu có nhắc BỘ PHẬN răng miệng kèm một
# CẢM GIÁC khó chịu, nhưng không trúng từ khóa dịch vụ cụ thể nào. Khi đó nên đưa
# ra lựa chọn có cấu trúc để chốt dịch vụ, thay vì bó tay báo "chưa rõ triệu chứng".
_DENTAL_PARTS = ["răng", "nướu", "lợi", "hàm", "chân răng", "hàm răng"]
_DISCOMFORT = ["đau", "khó chịu", "ê", "ê buốt", "buốt", "nhức", "cộm",
               "khi ăn", "khi nhai", "nhai", "sưng", "chảy máu", "nhạy cảm", "khó ăn"]


def mentions_dental_discomfort(text: str) -> bool:
    """True nếu câu nhắc tới bộ phận răng miệng + một cảm giác khó chịu.

    Dùng cho fallback khi classify_symptoms không đủ điểm: vẫn nhận ra đây là vấn
    đề răng miệng để hỏi có cấu trúc. Khớp KHÔNG phân biệt dấu (bắt cả gõ thiếu dấu).
    """
    norm_na = _strip_accents(_normalize_clausal(text))
    has_part = any(_match_kind(norm_na, _strip_accents(p), accent_free=True) == "hit"
                   for p in _DENTAL_PARTS)
    # Cảm giác khó chịu phải KHÔNG bị phủ định: "răng tôi không đau" -> False.
    has_feel = any(_match_kind(norm_na, _strip_accents(f), accent_free=True) == "hit"
                   for f in _DISCOMFORT)
    return has_part and has_feel


# ---------------------------------------------------------------------------
# CÂU HỎI THÔNG TIN: "trám răng là khám gì?", "nội nha khám gì?", "niềng răng là gì?"
# -> nhận diện (cụm hỏi thông tin) + (tên/từ khóa dịch vụ) để trả về mô tả dịch vụ.
# ---------------------------------------------------------------------------
# Các cụm cho thấy người dùng đang HỎI THÔNG TIN (không dấu). Cố ý bỏ "làm gì"
# vì dễ trùng câu than phiền ("đau quá không biết làm gì").
_INFO_TRIGGERS = [
    "kham gi", "kham nhung gi", "kham the nao", "kham nhu the nao",
    "la gi", "la benh gi", "la dich vu gi", "gom gi", "gom nhung gi",
    "bao gom gi", "dieu tri gi", "dieu tri nhung gi", "chua gi",
    "nhu the nao", "de lam gi", "co tac dung gi",
    # "trám răng là CÁI GÌ", "nội nha CHỮA CÁI GÌ"
    "la cai gi", "cai gi", "kham cai gi", "chua cai gi", "dieu tri cai gi",
    "la sao", "the nao",
]

# Viết tắt kiểu chat: "là cái g", "niềng răng là j" -> quy về "gi" để bắt được.
_CHAT_SHORTHAND = {"g": "gi", "j": "gi", "ji": "gi", "z": "gi", "wa": "qua"}


def _normalize_chat(text: str) -> str:
    """Chuẩn hóa + bỏ dấu + giãn viết tắt (chỉ dùng cho nhận diện câu hỏi thông tin)."""
    toks = _strip_accents(_normalize(text)).split()
    return " ".join(_CHAT_SHORTHAND.get(t, t) for t in toks)

# Token quá chung -> bỏ khi so khớp tên/từ khóa dịch vụ (tránh nhiễu).
_MENTION_STOP = set(
    "rang kham gi la lam nha khoa va cho bi dieu tri chua cua nhung the nao nhu "
    "ban toi o khi mot cac dich vu benh vung de co tac dung gom bao".split()
)


def is_info_question(text: str) -> bool:
    """Câu có mang ý HỎI THÔNG TIN về một dịch vụ? (khớp không phân biệt dấu)."""
    na = _normalize_chat(text)
    return any(t in na for t in _INFO_TRIGGERS)


def _mention_tokens(phrases, strip: bool) -> set:
    """Tập token đặc trưng từ các cụm, đã bỏ token chung (lọc theo bản không dấu).

    strip=False giữ token CÓ DẤU (để phân biệt 'trồng' vs 'trong'); strip=True bỏ
    dấu (bắt cả khi người dùng gõ thiếu dấu).
    """
    toks = set()
    for phrase in phrases:
        for t in _normalize(phrase).split():
            base = _strip_accents(t)
            if not base or base in _MENTION_STOP:
                continue
            toks.add(base if strip else t)
    return toks


def find_service_mention(text: str):
    """Tìm mã dịch vụ được nhắc tới trong câu (khớp tên/từ khóa). None nếu không rõ.

    Ưu tiên khớp CÓ DẤU; nếu không ra kết quả mới thử bản bỏ dấu.
    """
    for strip in (False, True):
        msg = _mention_tokens([text], strip)
        best, best_score = None, 0
        for code, dept in DEPARTMENTS.items():
            dept_tokens = _mention_tokens(
                [dept.get("name", "")] + list(dept.get("keywords", [])), strip)
            score = len(msg & dept_tokens)
            if score > best_score:
                best, best_score = code, score
        if best_score > 0:
            return best
    return None


def info_question_service(text: str):
    """Nếu câu là câu hỏi thông tin VỀ một dịch vụ cụ thể -> trả mã dịch vụ, else None."""
    if not is_info_question(text):
        return None
    return find_service_mention(text)


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
