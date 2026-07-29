"""
Thử engine LLM của triage — gõ câu tiếng Việt, xem NGAY hai engine trả lời gì.

Mục đích: kiểm chứng bằng tay rằng bot đã hiểu NGỮ NGHĨA chứ không còn dò từ
khóa. Mỗi câu chạy song song hai engine rồi in cạnh nhau:

    llm  — gọi mô hình qua OpenRouter (app/triage/llm.py)
    v2   — rule-based, chấm điểm theo từ khóa (bản cũ)

Chỗ đáng nhìn nhất là những câu **v2 trả rỗng mà llm vẫn ra đúng dịch vụ**:
đó chính là phần rule-based mù, và là lý do dự án cắm LLM.

    ./.venv/bin/python scripts/try_llm.py                 # gõ câu tương tác
    ./.venv/bin/python scripts/try_llm.py "câu cần thử"   # chạy một câu
    ./.venv/bin/python scripts/try_llm.py --suite         # bộ câu mẫu KHÔNG chứa từ khóa

Cần OPENROUTER_API_KEY trong .env. Mỗi câu = 1 lượt gọi API.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.triage import llm
from app import triage
from app.core.catalog import DEPARTMENTS

# Câu mẫu CỐ Ý viết vòng vo, không dùng thuật ngữ nha khoa nào có trong bộ từ
# khóa của triage.py — để thấy rõ trần của rule-based.
SUITE = [
    "cắn miếng táo mà buốt tận óc, mấy hôm nay ăn gì cũng sợ",
    "bàn chải lúc nào cũng dính máu dù tôi chải rất nhẹ",
    "người yêu bảo hơi thở tôi có mùi khó chịu",
    "đau giật từng hồi, cứ đặt lưng xuống là nhức hơn",
    "chiếc răng cửa sẫm màu hơn hẳn mấy cái bên cạnh",
    "chỗ trống sau khi mất răng làm tôi nhai một bên suốt",
    "hai hàm chen chúc lên nhau, cười lên nhìn không đều",
    "toi khong bi dau gi ca, chi muon di kiem tra cho yen tam",
    "phòng khám mở cửa mấy giờ vậy shop",
]

W = 34  # bề rộng cột tên dịch vụ


def _name(code):
    return DEPARTMENTS.get(code, {}).get("name", code)


def probe(text):
    """Chạy một câu qua cả hai engine, in bảng so sánh."""
    t0 = time.perf_counter()
    r_llm = triage.classify_symptoms(text, version="llm")
    ms_llm = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    r_v2 = triage.classify_symptoms(text, version="v2")
    ms_v2 = (time.perf_counter() - t0) * 1000

    top_llm = _name(r_llm[0]["code"]) if r_llm else "— (không nhận ra)"
    top_v2 = _name(r_v2[0]["code"]) if r_v2 else "— (không nhận ra)"

    print(f'\n  "{text}"')
    print(f"    llm  {top_llm:<{W}} {triage.confidence_level(r_llm):<7} {ms_llm:7.0f} ms")
    print(f"    v2   {top_v2:<{W}} {triage.confidence_level(r_v2):<7} {ms_v2:7.2f} ms")

    if r_llm:
        # Bằng chứng model trích từ chính câu của người dùng -> giải thích được
        # vì sao ra nhãn đó, thay vì "hộp đen".
        evidence = r_llm[0].get("matched") or []
        if evidence:
            print(f"    ↳ căn cứ: {' · '.join(evidence)}")
        if len(r_llm) > 1:
            print(f"    ↳ phương án khác: {', '.join(_name(r['code']) for r in r_llm[1:])}")

    if r_llm and not r_v2:
        print("    ✅ LLM bắt được câu mà rule-based MÙ HOÀN TOÀN")
    elif not r_llm and not r_v2:
        print("    ○ cả hai đều không gán nhãn (đúng nếu câu không phải triệu chứng)")
    elif r_llm and r_v2 and r_llm[0]["code"] != r_v2[0]["code"]:
        print("    ⚠️  hai engine cho kết quả KHÁC nhau")


def main():
    args = [a for a in sys.argv[1:] if a != "--suite"]
    suite = "--suite" in sys.argv

    if not llm.is_enabled():
        print("LLM đang TẮT — thiếu OPENROUTER_API_KEY trong .env (hoặc LLM_ENABLED=0).")
        print("Không có nó thì script này chỉ so v2 với chính nó.")
        return 1

    print(f"Model: {llm.model()}   |   engine mặc định của app: {triage.default_version()}")

    if suite:
        for text in SUITE:
            probe(text)
        if llm.LAST_ERROR:
            print(f"\n[!] Lượt gọi gần nhất lỗi: {llm.LAST_ERROR}")
        return 0

    if args:
        probe(" ".join(args))
        return 0

    # Chế độ tương tác
    print("Gõ câu triệu chứng rồi Enter (Ctrl-C để thoát).")
    while True:
        try:
            text = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if text:
            probe(text)


if __name__ == "__main__":
    sys.exit(main())
