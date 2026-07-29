"""
Lớp gọi LLM — cổng ra DUY NHẤT của dự án tới mô hình ngôn ngữ.

Dùng **OpenRouter** (https://openrouter.ai) vì nó nói giao thức OpenAI
`/chat/completions`, nên đổi sang model nào (Gemini, GPT, Claude, Llama...) chỉ
là đổi biến môi trường `LLM_MODEL`, không phải sửa code.

Biến môi trường (đặt trong `.env`):

    OPENROUTER_API_KEY   khóa `sk-or-v1-...`. KHÔNG có -> LLM tắt, hệ thống
                         chạy hoàn toàn bằng rule-based như trước.
    LLM_MODEL            mã model trên OpenRouter (mặc định: xem DEFAULT_MODEL).
    LLM_ENABLED          "0"/"false" để tắt cưỡng bức dù có key (dùng cho test).
    LLM_TIMEOUT          giây, mặc định 8. Quá hạn -> coi như lỗi -> fallback.
    LLM_BASE_URL         đổi endpoint nếu muốn dùng nhà cung cấp khác.

Nguyên tắc: **hàm ở đây KHÔNG BAO GIỜ ném exception ra ngoài**. Mọi sự cố
(mất mạng, hết credit, JSON hỏng) đều trả `None` để tầng trên tự động quay về
bộ luật từ khóa — chatbot y tế không được phép chết vì API bên thứ ba.

Chỉ dùng thư viện chuẩn (`urllib`) -> không thêm dependency.
"""

import json
import os
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
# Model mặc định: rẻ, nhanh, tiếng Việt tốt — đủ cho bài toán phân loại 1 nhãn.
DEFAULT_MODEL = "google/gemini-2.5-flash-lite"
DEFAULT_TIMEOUT = 8.0

# Lỗi gần nhất (đọc ở /admin hoặc khi debug). Không log key ra ngoài.
LAST_ERROR = None


def api_key() -> str:
    return (os.environ.get("OPENROUTER_API_KEY") or "").strip()


def model() -> str:
    return (os.environ.get("LLM_MODEL") or "").strip() or DEFAULT_MODEL


def base_url() -> str:
    return (os.environ.get("LLM_BASE_URL") or "").strip() or DEFAULT_BASE_URL


def timeout() -> float:
    try:
        return float(os.environ.get("LLM_TIMEOUT") or DEFAULT_TIMEOUT)
    except ValueError:
        return DEFAULT_TIMEOUT


def is_enabled() -> bool:
    """LLM có được bật không? Cần (1) có API key và (2) không bị tắt cưỡng bức."""
    flag = (os.environ.get("LLM_ENABLED") or "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    return bool(api_key())


def status() -> dict:
    """Tóm tắt cấu hình để hiển thị/chẩn đoán (KHÔNG chứa API key)."""
    return {
        "enabled": is_enabled(),
        "model": model() if is_enabled() else None,
        "has_key": bool(api_key()),
        "last_error": LAST_ERROR,
    }


def _post(path: str, payload: dict):
    """POST JSON tới OpenRouter. Trả dict kết quả, hoặc None nếu có bất kỳ lỗi nào."""
    global LAST_ERROR
    key = api_key()
    if not key:
        LAST_ERROR = "thiếu OPENROUTER_API_KEY"
        return None

    req = urllib.request.Request(
        base_url().rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # OpenRouter dùng 2 header này để gắn nhãn ứng dụng gọi API.
            "HTTP-Referer": "https://github.com/shi-nha-khoa",
            "X-Title": "Tro ly Nha khoa SHI",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        LAST_ERROR = None
        return data
    except urllib.error.HTTPError as e:
        # Lấy message lỗi của OpenRouter (hết credit, sai model...) cho dễ debug.
        try:
            detail = e.read().decode("utf-8")[:300]
        except Exception:
            detail = ""
        LAST_ERROR = f"HTTP {e.code}: {detail}"
    except Exception as e:  # timeout, DNS, JSON hỏng...
        LAST_ERROR = f"{type(e).__name__}: {e}"
    return None


def chat(system: str, user: str, max_tokens: int = 300, temperature: float = 0.0):
    """Một lượt hỏi–đáp. Trả về text của model, hoặc None nếu lỗi.

    `temperature=0` để kết quả ỔN ĐỊNH — bài toán phân loại cần tái lập được
    khi chấm điểm (eval), không cần sáng tạo.
    """
    data = _post("/chat/completions", {
        "model": model(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    })
    if not data:
        return None
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        global LAST_ERROR
        LAST_ERROR = f"phản hồi không đúng định dạng: {str(data)[:200]}"
        return None


def _extract_json(text: str):
    """Cắt lấy object JSON đầu tiên trong text (phòng khi model bọc ```json ... ```)."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def chat_json(system: str, user: str, max_tokens: int = 300):
    """Như `chat()` nhưng ép kết quả về dict JSON. None nếu lỗi/không parse được."""
    global LAST_ERROR
    raw = chat(system, user, max_tokens=max_tokens)
    if raw is None:
        return None
    parsed = _extract_json(raw)
    if parsed is None:
        LAST_ERROR = f"không parse được JSON: {raw[:200]}"
    return parsed
