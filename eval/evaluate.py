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
    errors = []
    latencies = []

    for r in rows:
        gold = r["label"]
        t0 = time.perf_counter()
        pred = predict(r["text"], version)
        latencies.append((time.perf_counter() - t0) * 1000.0)

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
        "macro_precision": macro_p,
        "macro_recall": macro_r,
        "macro_f1": macro_f1,
        "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
        "per_class": per_class,
        "errors": errors,
    }


def _pct(x):
    return f"{x * 100:5.1f}%"


def render_markdown(rows, res_v1, res_v2):
    lines = []
    lines.append("# Kết quả đánh giá Triage engine — Nha khoa SHI\n")
    lines.append(f"- Số mẫu (dataset): **{res_v2['n']}**")
    lines.append(f"- Số lớp (dịch vụ): **{len(LABELS)}**")
    lines.append(f"- Sinh tự động bởi `eval/evaluate.py`\n")

    lines.append("## 1. So sánh tổng thể hai phiên bản\n")
    lines.append("| Chỉ số | v1 (có dấu) | v2 (không phân biệt dấu) |")
    lines.append("|---|---|---|")
    lines.append(f"| Accuracy | {_pct(res_v1['accuracy'])} | **{_pct(res_v2['accuracy'])}** |")
    lines.append(f"| Macro Precision | {_pct(res_v1['macro_precision'])} | **{_pct(res_v2['macro_precision'])}** |")
    lines.append(f"| Macro Recall | {_pct(res_v1['macro_recall'])} | **{_pct(res_v2['macro_recall'])}** |")
    lines.append(f"| Macro F1 | {_pct(res_v1['macro_f1'])} | **{_pct(res_v2['macro_f1'])}** |")
    lines.append(f"| Thời gian TB (ms/câu) | {res_v1['avg_latency_ms']:.3f} | {res_v2['avg_latency_ms']:.3f} |")
    lines.append("")

    lines.append("## 2. Precision / Recall / F1 theo từng dịch vụ (v2)\n")
    lines.append("| Dịch vụ | Precision | Recall | F1 | Số mẫu |")
    lines.append("|---|---|---|---|---|")
    for c in LABELS:
        m = res_v2["per_class"][c]
        lines.append(f"| {LABEL_NAME[c]} | {_pct(m['precision'])} | {_pct(m['recall'])} | "
                     f"{_pct(m['f1'])} | {m['support']} |")
    lines.append("")

    lines.append("## 3. Các trường hợp v2 phân loại sai (error analysis)\n")
    if not res_v2["errors"]:
        lines.append("_Không có lỗi nào trên tập hiện tại._")
    else:
        lines.append("| Câu nhập | Nhãn đúng | Dự đoán |")
        lines.append("|---|---|---|")
        for e in res_v2["errors"]:
            pred = LABEL_NAME.get(e["pred"], "(không nhận ra)")
            lines.append(f"| {e['text']} | {LABEL_NAME[e['gold']]} | {pred} |")
    lines.append("")
    return "\n".join(lines)


def main():
    rows = load_dataset(DATASET_PATH)
    res_v1 = evaluate(rows, "v1")
    res_v2 = evaluate(rows, "v2")

    md = render_markdown(rows, res_v1, res_v2)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        f.write(md + "\n")

    # Tóm tắt ra terminal
    print(f"Dataset: {res_v2['n']} mẫu, {len(LABELS)} lớp\n")
    print(f"{'Phiên bản':<28}{'Accuracy':>10}{'MacroF1':>10}{'ms/câu':>10}")
    for r in (res_v1, res_v2):
        print(f"{r['version']:<28}{_pct(r['accuracy']):>10}{_pct(r['macro_f1']):>10}"
              f"{r['avg_latency_ms']:>10.3f}")
    print(f"\nĐã ghi bảng chi tiết -> {os.path.relpath(RESULTS_PATH, ROOT)}")


if __name__ == "__main__":
    main()
