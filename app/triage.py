"""
Triage engine — phần "hàm lượng AI" của đề tài (phòng khám Nha khoa SHI).

Nhiệm vụ: nhận mô tả triệu chứng răng miệng bằng tiếng Việt -> phân loại đúng
NHÓM DỊCH VỤ nha khoa (sâu răng, nội nha, nha chu, chỉnh nha...).

Có BA phiên bản engine, dùng chung một định dạng kết quả nên thay nhau được và
so sánh được khi ĐÁNH GIÁ:

  - v1  : rule-based, so khớp từ khóa trên văn bản đã viết thường (bản gốc).
  - v2  : như v1 nhưng so khớp KHÔNG phân biệt dấu (accent-insensitive),
          bắt được cả khi người dùng gõ thiếu dấu — rất phổ biến ở tiếng Việt.
  - llm : gọi mô hình ngôn ngữ qua OpenRouter (xem app/llm.py) để hiểu NGỮ NGHĨA
          câu tiếng Việt, không phụ thuộc việc câu có chứa đúng từ khóa hay không.

Phiên bản dùng trong sản phẩm do môi trường quyết định (`default_version()`):
có `OPENROUTER_API_KEY` -> chạy `llm`, không có -> `v2`. LLM lỗi/timeout/hết
credit thì TỰ ĐỘNG quay về v2 — chatbot không bao giờ chết vì API bên ngoài.
"""

import re
import threading
import unicodedata
from . import llm
from .data import DEPARTMENTS

DEFAULT_VERSION = "v2"   # engine rule-based dùng làm nền/fallback
LLM_VERSION = "llm"      # engine gọi mô hình ngôn ngữ


def default_version() -> str:
    """Engine dùng trong sản phẩm: 'llm' nếu đã cấu hình API key, else 'v2'."""
    return LLM_VERSION if llm.is_enabled() else DEFAULT_VERSION

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


def classify_symptoms(text: str, version: str = None):
    """Phân loại triệu chứng -> danh sách dịch vụ kèm điểm số, giảm dần.

    Trả về list các dict: [{code, name, desc, score, matched: [...]}, ...]

    version=None : dùng engine mặc định của môi trường (xem default_version()).
    version='v1' : so khớp từ khóa có dấu.
    version='v2' : so khớp không phân biệt dấu (bắt cả văn bản gõ thiếu dấu).
    version='llm': hỏi mô hình ngôn ngữ; lỗi/không chắc -> tự fallback về v2.
    """
    version = version or default_version()
    if version == LLM_VERSION:
        results = classify_with_llm(text)
        if results is not None:
            return results
        version = DEFAULT_VERSION  # LLM hỏng -> quay về rule-based
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
    Luôn chạy bằng luật từ khóa (kể cả khi engine chính là LLM): ở đây ta cần biết
    người dùng đã NHẮC TỚI dịch vụ nào, mà LLM thì cố tình không trả về nhãn bị phủ định.
    """
    if version == LLM_VERSION:
        version = DEFAULT_VERSION
    _, negated = _score(text, version)
    return negated


def best_department(text: str, version: str = None):
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
    # Engine LLM tự nói mức tin cậy của nó -> tin theo, không suy ra từ điểm số
    # (điểm của LLM là thứ hạng quy ước, không cùng thang với rule-based).
    stated = results[0].get("confidence")
    if stated in ("high", "medium", "low"):
        return stated
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
# ENGINE LLM — hiểu NGỮ NGHĨA thay vì đếm từ khóa.
#
# Rule-based chỉ đúng khi câu chứa đúng cụm từ đã liệt kê; câu nói vòng
# ("cắn miếng táo mà buốt tận óc") thì trượt. LLM đọc hiểu cả câu rồi CHỌN
# trong đúng danh mục dịch vụ của phòng khám — nó KHÔNG được tự bịa nhãn mới,
# KHÔNG chẩn đoán, KHÔNG kê đơn (phần chặn nội dung vẫn do app/safety.py giữ).
# ---------------------------------------------------------------------------

# Điểm quy ước gán cho các nhãn LLM trả về, theo thứ hạng. Chỉ để xếp hạng và
# cho phần code cũ (đọc field "score") chạy nguyên vẹn.
_LLM_RANK_SCORES = [10, 7, 4]

# Cache theo văn bản: một lượt chat gọi classify_symptoms 2–3 lần cho CÙNG câu
# (định tuyến state, phát hiện triệu chứng mới...). Không cache thì trả tiền
# và chờ mạng nhiều lần cho một câu hỏi.
_LLM_CACHE = {}
_LLM_CACHE_MAX = 256
_LLM_CACHE_LOCK = threading.Lock()


def _llm_system_prompt() -> str:
    """Prompt hệ thống: liệt kê đúng danh mục dịch vụ + ràng buộc đầu ra JSON."""
    catalog = "\n".join(
        f'- {code}: {d["name"]} — {d["desc"]}' for code, d in DEPARTMENTS.items()
    )
    return (
        "Bạn là bộ phân loại (triage) của một PHÒNG KHÁM NHA KHOA ở Việt Nam. "
        "Nhiệm vụ: đọc mô tả triệu chứng răng miệng bằng tiếng Việt (có thể thiếu "
        "dấu, viết tắt, sai chính tả) và chọn NHÓM DỊCH VỤ phù hợp nhất.\n\n"
        f"Danh mục dịch vụ (chỉ được chọn trong đây):\n{catalog}\n\n"
        "QUY TẮC:\n"
        "1. Chỉ trả mã dịch vụ có trong danh mục. Tuyệt đối không bịa mã mới.\n"
        "2. Không chẩn đoán bệnh, không kê đơn thuốc, không nêu tên thuốc.\n"
        "3. Tôn trọng phủ định: 'tôi không bị đau răng' KHÔNG phải triệu chứng "
        "đau răng -> không trả mã đó.\n"
        "4. Câu không liên quan răng miệng (chào hỏi, hỏi giá, hỏi đường...) -> "
        'trả danh sách rỗng.\n'
        "5. confidence: 'high' khi chắc chắn một dịch vụ; 'medium' khi còn phân "
        "vân giữa vài dịch vụ; 'low' khi không đủ thông tin.\n\n"
        "CHỈ trả JSON đúng dạng:\n"
        '{"services": [{"code": "<mã>", "evidence": ["<cụm từ trong câu>"]}], '
        '"confidence": "high|medium|low"}\n'
        "Xếp services theo độ phù hợp giảm dần, tối đa 3 mã."
    )


def _llm_results(payload):
    """Đổi JSON của model -> đúng định dạng của classify_symptoms(). None nếu hỏng."""
    if not isinstance(payload, dict):
        return None
    services = payload.get("services")
    if not isinstance(services, list):
        return None

    confidence = payload.get("confidence")
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"

    results, seen = [], set()
    for item in services[:len(_LLM_RANK_SCORES)]:
        code = item.get("code") if isinstance(item, dict) else item
        # Bỏ mã model bịa ra hoặc trả trùng.
        if code not in DEPARTMENTS or code in seen:
            continue
        seen.add(code)
        evidence = item.get("evidence") if isinstance(item, dict) else None
        dept = DEPARTMENTS[code]
        results.append({
            "code": code,
            "name": dept["name"],
            "desc": dept["desc"],
            "score": _LLM_RANK_SCORES[len(results)],
            "matched": [str(e) for e in evidence][:5] if isinstance(evidence, list) else [],
            "confidence": confidence,
            "source": LLM_VERSION,
        })
    # Model bảo có dịch vụ nhưng mã đều sai -> coi như hỏng, để tầng trên fallback.
    if services and not results:
        return None
    return results


def _cache_get(key):
    with _LLM_CACHE_LOCK:
        return _LLM_CACHE.get(key)


def _cache_put(key, value):
    with _LLM_CACHE_LOCK:
        if len(_LLM_CACHE) >= _LLM_CACHE_MAX:
            _LLM_CACHE.clear()  # cache demo: đầy thì xoá sạch, đủ dùng
        _LLM_CACHE[key] = value


def clear_llm_cache():
    """Xoá cache LLM (dùng trong test hoặc khi đổi model lúc đang chạy)."""
    with _LLM_CACHE_LOCK:
        _LLM_CACHE.clear()


def classify_with_llm(text: str):
    """Phân loại bằng LLM. Trả về list KẾT QUẢ (có thể rỗng), hoặc None nếu KHÔNG
    gọi được model — phân biệt hai ca này rất quan trọng:

        []   = model đã trả lời và khẳng định "không có dịch vụ nào phù hợp"
        None = LLM tắt/lỗi/timeout -> tầng trên phải fallback sang rule-based
    """
    if not llm.is_enabled():
        return None
    key = _normalize(text or "")
    if not key:
        return None

    cached = _cache_get(key)
    if cached is not None:
        return cached

    payload = llm.chat_json(_llm_system_prompt(), (text or "").strip()[:1000])
    if payload is None:
        return None
    results = _llm_results(payload)
    if results is None:
        return None
    _cache_put(key, results)
    return results
