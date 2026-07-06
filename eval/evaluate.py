"""
Đánh giá ĐỊNH LƯỢNG cho Triage engine của Nha khoa SHI.

Chạy bộ phân loại trên dataset gán nhãn (eval/dataset.jsonl), so dự đoán
top-1 với nhãn vàng (gold label) và tính:
  - Accuracy (độ chính xác tổng thể)
  - Precision / Recall / F1 cho từng lớp + Macro-average
  - Thời gian phản hồi trung bình (ms/câu)
So sánh HAI phiên bản engine: v1 (so khớp có dấu) và v2 (không phân biệt dấu).

Chạy:
    ./.venv/bin/python eval/evaluate.py
Kết quả in ra màn hình và ghi vào eval/results.md (bảng Markdown).

Chỉ dùng thư viện chuẩn -> không cần cài thêm gì.
"""

import json
import os
import sys
import time

# Cho phép import triage/data từ thư mục gốc dự án.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import triage  # noqa: E402
from data import DEPARTMENTS  # noqa: E402

DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset.jsonl")
COMPLEX_PATH = os.path.join(os.path.dirname(__file__), "dataset_complex.jsonl")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "results.md")

LABELS = list(DEPARTMENTS.keys())
LABEL_NAME = {code: d["name"] for code, d in DEPARTMENTS.items()}


def load_dataset(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def ranked_codes(text, version):
    """Danh sách mã dịch vụ theo điểm giảm dần (rỗng nếu không nhận ra gì)."""
    return [r["code"] for r in triage.classify_symptoms(text, version=version)]


def predict(text, version):
    """Top-1 dự đoán; None nếu engine không nhận ra (đếm là sai)."""
    top = triage.best_department(text, version=version)
    return top["code"] if top else None


def evaluate(rows, version):
    """Trả về dict gồm accuracy, latency và per-class P/R/F1."""
    # tp/fp/fn cho từng lớp
    tp = {c: 0 for c in LABELS}
    fp = {c: 0 for c in LABELS}
    fn = {c: 0 for c in LABELS}

    correct = 0
    correct_top2 = 0
    errors = []
    latencies = []

    for r in rows:
        gold = r["label"]
        t0 = time.perf_counter()
        ranked = ranked_codes(r["text"], version)
        latencies.append((time.perf_counter() - t0) * 1000.0)
        pred = ranked[0] if ranked else None

        if gold in ranked[:2]:
            correct_top2 += 1

        if pred == gold:
            correct += 1
            tp[gold] += 1
        else:
            fn[gold] += 1
            if pred is not None:
                fp[pred] += 1
            errors.append({"text": r["text"], "gold": gold, "pred": pred})

    per_class = {}
    for c in LABELS:
        p = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) else 0.0
        rec = tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) else 0.0
        f1 = 2 * p * rec / (p + rec) if (p + rec) else 0.0
        per_class[c] = {"precision": p, "recall": rec, "f1": f1,
                        "support": tp[c] + fn[c]}

    macro_p = sum(v["precision"] for v in per_class.values()) / len(LABELS)
    macro_r = sum(v["recall"] for v in per_class.values()) / len(LABELS)
    macro_f1 = sum(v["f1"] for v in per_class.values()) / len(LABELS)

    return {
        "version": version,
        "n": len(rows),
        "accuracy": correct / len(rows) if rows else 0.0,
        "accuracy_top2": correct_top2 / len(rows) if rows else 0.0,
        "macro_precision": macro_p,
        "macro_recall": macro_r,
        "macro_f1": macro_f1,
        "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
        "per_class": per_class,
        "errors": errors,
    }


def evaluate_complex(rows, version):
    """Đánh giá tập câu PHỨC TẠP (ghép nhiều ý).

    Mỗi câu có nhãn CHÍNH (`label`) và tập dịch vụ HỢP LỆ (`accept`). Vì một câu
    nhắc nhiều dịch vụ, ta đo 3 chỉ số phù hợp với cách chatbot cho người dùng
    chọn trong vài gợi ý:
      - top1_exact   : top-1 trùng đúng nhãn chính.
      - top1_accept  : top-1 nằm trong tập dịch vụ hợp lệ (chọn 1 dịch vụ đúng).
      - top2_accept  : có ít nhất 1 trong top-2 nằm trong tập hợp lệ.
    """
    n = len(rows)
    top1_exact = top1_accept = top2_accept = 0
    detail = []
    for r in rows:
        gold = r["label"]
        accept = set(r.get("accept", [gold]))
        ranked = ranked_codes(r["text"], version)
        pred = ranked[0] if ranked else None
        e = pred == gold
        a1 = pred in accept
        a2 = any(c in accept for c in ranked[:2])
        top1_exact += e
        top1_accept += a1
        top2_accept += a2
        detail.append({"text": r["text"], "gold": gold, "accept": sorted(accept),
                       "top2": ranked[:2], "ok1": a1, "ok2": a2})
    return {
        "version": version, "n": n,
        "top1_exact": top1_exact / n if n else 0.0,
        "top1_accept": top1_accept / n if n else 0.0,
        "top2_accept": top2_accept / n if n else 0.0,
        "detail": detail,
    }


def _pct(x):
    return f"{x * 100:5.1f}%"


def render_markdown(rows, res_v1, res_v2, cx_rows, cx_v2):
    lines = []
    lines.append("# Kết quả đánh giá Triage engine — Nha khoa SHI\n")
    lines.append(f"- Tập câu ĐƠN-Ý (mỗi câu 1 dịch vụ): **{res_v2['n']}** câu, "
                 f"**{len(LABELS)}** lớp (dịch vụ).")
    lines.append(f"- Tập câu PHỨC TẠP (ghép 2-3 ý): **{cx_v2['n']}** câu.")
    lines.append(f"- Sinh tự động bởi `eval/evaluate.py`\n")

    lines.append("## 1. So sánh tổng thể hai phiên bản (tập câu đơn-ý)\n")
    lines.append("| Chỉ số | v1 (có dấu) | v2 (không phân biệt dấu) |")
    lines.append("|---|---|---|")
    lines.append(f"| Accuracy (top-1) | {_pct(res_v1['accuracy'])} | **{_pct(res_v2['accuracy'])}** |")
    lines.append(f"| Accuracy (top-2) | {_pct(res_v1['accuracy_top2'])} | **{_pct(res_v2['accuracy_top2'])}** |")
    lines.append(f"| Macro Precision | {_pct(res_v1['macro_precision'])} | **{_pct(res_v2['macro_precision'])}** |")
    lines.append(f"| Macro Recall | {_pct(res_v1['macro_recall'])} | **{_pct(res_v2['macro_recall'])}** |")
    lines.append(f"| Macro F1 | {_pct(res_v1['macro_f1'])} | **{_pct(res_v2['macro_f1'])}** |")
    lines.append(f"| Thời gian TB (ms/câu) | {res_v1['avg_latency_ms']:.3f} | {res_v2['avg_latency_ms']:.3f} |")
    lines.append("")

    lines.append("## 2. Precision / Recall / F1 theo từng dịch vụ (v2, tập đơn-ý)\n")
    lines.append("| Dịch vụ | Precision | Recall | F1 | Số mẫu |")
    lines.append("|---|---|---|---|---|")
    for c in LABELS:
        m = res_v2["per_class"][c]
        lines.append(f"| {LABEL_NAME[c]} | {_pct(m['precision'])} | {_pct(m['recall'])} | "
                     f"{_pct(m['f1'])} | {m['support']} |")
    lines.append("")

    lines.append("## 3. Các trường hợp v2 phân loại sai (error analysis, tập đơn-ý)\n")
    if not res_v2["errors"]:
        lines.append("_Không có lỗi nào trên tập hiện tại._")
    else:
        lines.append("| Câu nhập | Nhãn đúng | Dự đoán |")
        lines.append("|---|---|---|")
        for e in res_v2["errors"]:
            pred = LABEL_NAME.get(e["pred"], "(không nhận ra)")
            lines.append(f"| {e['text']} | {LABEL_NAME[e['gold']]} | {pred} |")
    lines.append("")

    lines.append("## 4. Tập câu PHỨC TẠP — ghép 2-3 ý (v2)\n")
    lines.append("Mỗi câu nhắc nhiều dịch vụ. `label` là dịch vụ chính; `accept` là mọi "
                 "dịch vụ hợp lệ được nhắc. Vì bot cho người dùng chọn trong vài gợi ý, "
                 "ta đo cả top-1 và top-2:\n")
    lines.append("| Chỉ số | Ý nghĩa | Kết quả (v2) |")
    lines.append("|---|---|---|")
    lines.append(f"| Top-1 đúng nhãn chính | top-1 == dịch vụ chính | {_pct(cx_v2['top1_exact'])} |")
    lines.append(f"| Top-1 chấp nhận được | top-1 là một dịch vụ hợp lệ | **{_pct(cx_v2['top1_accept'])}** |")
    lines.append(f"| Top-2 chấp nhận được | có dịch vụ hợp lệ trong top-2 | **{_pct(cx_v2['top2_accept'])}** |")
    lines.append("")
    lines.append("Chi tiết từng câu (top-2 dự đoán so với tập dịch vụ hợp lệ):\n")
    lines.append("| Câu ghép nhiều ý | Dịch vụ hợp lệ | Top-2 dự đoán | Top-1 OK | Top-2 OK |")
    lines.append("|---|---|---|:--:|:--:|")
    for d in cx_v2["detail"]:
        accept = ", ".join(LABEL_NAME.get(c, c) for c in d["accept"])
        top2 = " > ".join(LABEL_NAME.get(c, c) for c in d["top2"]) or "(không nhận ra)"
        lines.append(f"| {d['text']} | {accept} | {top2} | "
                     f"{'✅' if d['ok1'] else '❌'} | {'✅' if d['ok2'] else '❌'} |")
    lines.append("")
    return "\n".join(lines)


def main():
    rows = load_dataset(DATASET_PATH)
    res_v1 = evaluate(rows, "v1")
    res_v2 = evaluate(rows, "v2")

    cx_rows = load_dataset(COMPLEX_PATH)
    cx_v2 = evaluate_complex(cx_rows, "v2")

    md = render_markdown(rows, res_v1, res_v2, cx_rows, cx_v2)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        f.write(md + "\n")

    # Tóm tắt ra terminal
    print(f"Tập đơn-ý: {res_v2['n']} mẫu, {len(LABELS)} lớp | "
          f"Tập phức tạp: {cx_v2['n']} câu\n")
    print(f"{'Phiên bản':<28}{'Acc@1':>8}{'Acc@2':>8}{'MacroF1':>9}{'ms/câu':>9}")
    for r in (res_v1, res_v2):
        print(f"{r['version']:<28}{_pct(r['accuracy']):>8}{_pct(r['accuracy_top2']):>8}"
              f"{_pct(r['macro_f1']):>9}{r['avg_latency_ms']:>9.3f}")
    print(f"\nTập phức tạp (v2): top-1 chấp nhận {_pct(cx_v2['top1_accept'])}, "
          f"top-2 chấp nhận {_pct(cx_v2['top2_accept'])}, "
          f"top-1 đúng nhãn chính {_pct(cx_v2['top1_exact'])}")
    print(f"\nĐã ghi bảng chi tiết -> {os.path.relpath(RESULTS_PATH, ROOT)}")


if __name__ == "__main__":
    main()
