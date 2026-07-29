"""
Chuẩn hóa văn bản tiếng Việt — dùng chung cho triage, nlu, safety và chatbot.

Trước đây các hàm này nằm private trong `triage.py` (`_normalize`, `_strip_accents`)
rồi 3 module khác thò tay vào import — mỗi lần sửa triage là phải nhớ ai đang
mượn. Tách ra đây để nó là một tiện ích công khai, có chủ.

Hai phép biến đổi cốt lõi cho tiếng Việt:

  - normalize()     : viết thường, dấu câu -> khoảng trắng, gộp khoảng trắng.
  - strip_accents() : bỏ dấu ("răng sâu" -> "rang sau"), để bắt được cả khi người
                      dùng gõ thiếu dấu — rất phổ biến khi chat.
"""

import re
import unicodedata

# Ký tự KHÔNG phải chữ/số -> coi như khoảng trắng (tách từ, bỏ dấu câu).
_NON_WORD = re.compile(r"[^0-9a-zA-ZÀ-ỹà-ỹ]+", re.UNICODE)

# Mốc đánh dấu RANH GIỚI MỆNH ĐỀ, thay cho dấu câu đã bị normalize() xoá.
# Cần cho việc xét phủ định: "có bất thường KHÔNG, khám tổng quát" — chữ "không"
# ở đây kết thúc mệnh đề trước, không phủ định "khám tổng quát".
CLAUSE_BREAK = "brk"
_CLAUSE_SEP = re.compile(r"[,.;:!?…\n]+")


def normalize(text: str) -> str:
    """Viết thường, đổi dấu câu thành khoảng trắng, gộp khoảng trắng."""
    return " ".join(_NON_WORD.sub(" ", (text or "").lower()).split())


def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt: 'răng sâu' -> 'rang sau' (giữ chữ 'đ' -> 'd')."""
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def contains_word(haystack: str, needle: str) -> bool:
    """Khớp theo RANH GIỚI TỪ (whole-word), tránh 'chân răng' chứa 'hàn răng'.

    Cả hai chuỗi phải đã đi qua normalize() (token cách nhau đúng 1 khoảng trắng).
    """
    return f" {needle} " in f" {haystack} "


def normalize_clausal(text: str) -> str:
    """Như normalize() nhưng GIỮ ranh giới mệnh đề dưới dạng token `brk`."""
    parts = (normalize(p) for p in _CLAUSE_SEP.split(text or ""))
    return f" {CLAUSE_BREAK} ".join(p for p in parts if p)
