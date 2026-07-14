"""
Kiểm tra CHẤT LƯỢNG dataset đánh giá — chạy trước khi tin vào số liệu eval.

Bắt 4 loại lỗi làm sai lệch kết quả đánh giá:
  1. TRÙNG Y HỆT      — cùng một câu bị chép 2 lần (thổi phồng support của 1 lớp).
  2. TRÙNG NỘI DUNG   — chỉ đổi vài từ đệm ("Bé..." vs "Con tôi..."), thực chất
                        vẫn là một mẫu -> mô hình không hề được test thêm gì.
  3. NHÃN LẠ          — label không có trong DEPARTMENTS.
  4. LỆCH PHÂN BỐ     — lớp nhiều/ít mẫu quá chênh (macro-F1 mất ý nghĩa).

LƯU Ý: câu viết THIẾU DẤU không bị coi là trùng với bản có dấu — đó là mẫu CỐ Ý
để đo v1 (có dấu) vs v2 (không phân biệt dấu). Vì vậy khoá so trùng giữ nguyên dấu;
chỉ khi hai câu giống nhau CẢ dấu lẫn từ mới tính là trùng y hệt.

Chạy:
    ./.venv/bin/python eval/check_dataset.py
Trả exit code 1 nếu có lỗi -> dùng được trong CI / pre-commit.
"""

import json
import os
import sys
from itertools import combinations

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.data import DEPARTMENTS  # noqa: E402
from app.triage import _normalize, _strip_accents  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["dataset.jsonl", "dataset_complex.jsonl", "dataset_negation.jsonl"]

# Ngưỡng trùng nội dung: tỉ lệ token chung (Jaccard) giữa 2 câu, tính trên bản
# ĐÃ BỎ DẤU + bỏ từ đệm. >= 0.80 nghĩa là gần như cùng một câu.
NEAR_DUP_THRESHOLD = 0.80

# Từ đệm không mang thông tin phân loại -> loại trước khi so trùng nội dung, để
# "Bé bị đau răng..." và "Con tôi bị đau răng..." lộ ra là cùng nội dung.
_FILLER = set(
    "toi em minh anh chi ba ong con be chau nha muon can di cho xin a oi voi va "
    "la bi co duoc lam qua lam nhieu rat hoi kha lai luon nua the nay do ay "
    "mot hai cai chiec o tai khi thi ma nhung cua se da dang cu deu tien".split()
)


def load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if line:
                rows.append((i, json.loads(line)))
    return rows


def content_key(text):
    """Tập token mang NGHĨA của câu (bỏ dấu, bỏ từ đệm) — dùng so trùng nội dung."""
    toks = _strip_accents(_normalize(text)).split()
    return {t for t in toks if t not in _FILLER}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def check_file(path, problems):
    name = os.path.basename(path)
    if not os.path.exists(path):
        return []
    rows = load(path)

    # 1. Trùng y hệt (so trên câu đã chuẩn hoá nhưng GIỮ dấu).
    seen = {}
    for ln, r in rows:
        key = _normalize(r["text"])
        if key in seen:
            problems.append(f"[{name}] TRÙNG Y HỆT: dòng {ln} lặp lại dòng {seen[key]}"
                            f" — {r['text']!r}")
        else:
            seen[key] = ln

    # 2. Trùng nội dung (chỉ khác từ đệm).
    keyed = [(ln, r, content_key(r["text"])) for ln, r in rows]
    for (l1, r1, k1), (l2, r2, k2) in combinations(keyed, 2):
        sim = jaccard(k1, k2)
        if sim >= NEAR_DUP_THRESHOLD:
            problems.append(
                f"[{name}] TRÙNG NỘI DUNG ({sim:.0%}): dòng {l1} & {l2}\n"
                f"      {r1['text']!r}\n      {r2['text']!r}")

    # 3. Nhãn lạ. (Tập phủ định dùng schema khác: `negated` + `expect`.)
    for ln, r in rows:
        labels = list(r.get("negated", [])) + list(r.get("expect", []))
        if "label" in r:
            labels += [r["label"]] + list(r.get("accept", []))
        for lb in labels:
            if lb not in DEPARTMENTS:
                problems.append(f"[{name}] NHÃN LẠ ở dòng {ln}: {lb!r}")

    return rows


def check_balance(rows, problems):
    counts = {}
    for _, r in rows:
        counts[r["label"]] = counts.get(r["label"], 0) + 1
    for code in DEPARTMENTS:
        counts.setdefault(code, 0)
    lo, hi = min(counts.values()), max(counts.values())
    if hi - lo > max(2, hi * 0.25):
        problems.append(f"[dataset.jsonl] LỆCH PHÂN BỐ: ít nhất {lo}, nhiều nhất {hi} "
                        f"mẫu/lớp — macro-F1 sẽ bị lớp đông chi phối.")
    return counts


def main():
    problems = []
    main_rows = check_file(os.path.join(HERE, "dataset.jsonl"), problems)
    check_file(os.path.join(HERE, "dataset_complex.jsonl"), problems)
    check_file(os.path.join(HERE, "dataset_negation.jsonl"), problems)

    counts = check_balance(main_rows, problems)

    print("Phân bố nhãn (dataset.jsonl):")
    for code, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {DEPARTMENTS[code]['name']:28} {n:3d}")
    print(f"  {'TỔNG':28} {sum(counts.values()):3d}\n")

    if problems:
        print(f"❌ Phát hiện {len(problems)} vấn đề:\n")
        for p in problems:
            print("  -", p)
        return 1

    print("✅ Không có câu trùng lặp / nhãn lạ / lệch phân bố.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
