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

from app import triage  # noqa: E402
from app.data import DEPARTMENTS  # noqa: E402

DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset.jsonl")
COMPLEX_PATH = os.path.join(os.path.dirname(__file__), "dataset_complex.jsonl")
NEGATION_PATH = os.path.join(os.path.dirname(__file__), "dataset_negation.jsonl")
HELDOUT_PATH = os.path.join(os.path.dirname(__file__), "dataset_heldout.jsonl")
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


def evaluate_negation(rows, version):
    """Đánh giá khả năng hiểu PHỦ ĐỊNH — "tôi không bị đau răng" KHÔNG phải triệu chứng.

    Mỗi câu có:
      - `negated`: dịch vụ người dùng LOẠI TRỪ  -> phải nằm trong negated_matches()
                   và TUYỆT ĐỐI không được engine gợi ý.
      - `expect` : dịch vụ engine ĐƯỢC PHÉP trả về (rỗng = không được trả gì).

    Đo 2 chỉ số:
      - no_false_positive: không gợi ý dịch vụ mà người dùng vừa phủ định (quan trọng
        nhất — đây chính là bug gốc: gõ "không bị đau răng" mà bot vẫn mời khám tủy).
      - correct         : vừa không gợi ý sai, vừa nhận đúng dịch vụ còn lại (nếu có).
    """
    n = len(rows)
    no_fp = correct = 0
    detail = []
    for r in rows:
        negated = set(r.get("negated", []))
        expect = set(r.get("expect", []))
        predicted = set(ranked_codes(r["text"], version))
        flagged = {x["code"] for x in triage.negated_matches(r["text"], version=version)}

        leaked = predicted & negated          # gợi ý đúng cái vừa bị phủ định -> SAI
        missed = expect - predicted           # bỏ sót dịch vụ thật sự cần
        ok_fp = not leaked
        ok_all = ok_fp and not missed
        no_fp += ok_fp
        correct += ok_all
        detail.append({"text": r["text"], "negated": sorted(negated),
                       "expect": sorted(expect), "pred": sorted(predicted),
                       "flagged": sorted(flagged), "ok": ok_all, "ok_fp": ok_fp})
    return {"version": version, "n": n,
            "no_false_positive": no_fp / n if n else 0.0,
            "correct": correct / n if n else 0.0,
            "detail": detail}


def _pct(x):
    return f"{x * 100:5.1f}%"


def render_heldout_section(ho_v2, in_v2):
    """Mục QUAN TRỌNG NHẤT về mặt khoa học: năng lực TỔNG QUÁT HÓA.

    Bộ từ khóa được tinh chỉnh DỰA TRÊN dataset.jsonl, nên điểm trên chính tập đó
    là điểm 'đã học thuộc', không phản ánh khả năng xử lý câu chưa từng thấy.
    dataset_heldout.jsonl gồm câu DIỄN GIẢI (không dùng đúng từ khóa nào), viết
    riêng để đo điều đó và CHỈ CHẠY MỘT LẦN, không dùng để chỉnh engine.
    """
    lines = []
    lines.append("## 6. Năng lực TỔNG QUÁT HÓA (held-out) — giới hạn của rule-based\n")
    lines.append("| Tập | Cách dùng | Accuracy (v2) | Macro F1 |")
    lines.append("|---|---|---|---|")
    lines.append(f"| `dataset.jsonl` | **đã dùng để tinh chỉnh từ khóa** | {_pct(in_v2['accuracy'])} "
                 f"| {_pct(in_v2['macro_f1'])} |")
    lines.append(f"| `dataset_heldout.jsonl` | **chưa từng dùng để chỉnh** (câu diễn giải) "
                 f"| **{_pct(ho_v2['accuracy'])}** | **{_pct(ho_v2['macro_f1'])}** |")
    lines.append("")
    lines.append("> ⚠️ **Đọc con số cho đúng.** Điểm gần tuyệt đối ở tập trên là điểm *trên chính "
                 "dữ liệu đã dùng để thêm từ khóa* — nó KHÔNG phải năng lực thật. Con số trung thực "
                 "là ở tập held-out.\n")
    none_cnt = sum(1 for e in ho_v2["errors"] if e["pred"] is None)
    wrong_cnt = len(ho_v2["errors"]) - none_cnt
    lines.append(f"Trong {len(ho_v2['errors'])} câu sai của tập held-out: **{none_cnt}** câu engine "
                 f"KHÔNG nhận ra gì (bot sẽ hỏi lại — hỏng nhẹ), **{wrong_cnt}** câu engine đoán "
                 f"SAI dịch vụ (nguy hiểm hơn: dẫn bệnh nhân tới sai bác sĩ).\n")
    lines.append("**Kết luận.** Rule-based chỉ đúng khi người dùng gõ *trúng* từ khóa đã liệt kê. "
                 "Với câu diễn giải (“buốt tận óc”, “bàn chải dính máu”, “răng chồng lên nhau”) nó "
                 "mù hoàn toàn. Thêm từ khóa chỉ chữa được phần ngọn — muốn vượt trần này phải dùng "
                 "NLU theo ngữ nghĩa, tức là điểm cắm LLM `triage.classify_with_llm()`.\n")
    lines.append("| Câu held-out engine bỏ sót / đoán sai | Nhãn đúng | Dự đoán |")
    lines.append("|---|---|---|")
    for e in ho_v2["errors"]:
        pred = LABEL_NAME.get(e["pred"], "_(không nhận ra)_")
        lines.append(f"| {e['text']} | {LABEL_NAME[e['gold']]} | {pred} |")
    lines.append("")
    return "\n".join(lines)


def render_negation_section(ng_v1, ng_v2):
    lines = []
    lines.append("## 5. Hiểu PHỦ ĐỊNH — “tôi không bị đau răng”\n")
    lines.append("Rule-based chấm điểm theo từ khóa sẽ khớp *“đau răng”* ngay cả khi câu "
                 "PHỦ ĐỊNH nó. Engine v2 chặn bằng cách bỏ qua từ khóa nằm sau từ phủ định "
                 "(chỉ nhìn ngược về trước, không vượt qua ranh giới mệnh đề — vì trong "
                 "tiếng Việt “không” đứng SAU thường là từ để **hỏi**: *“có sâu răng không?”*).\n")
    lines.append("| Chỉ số | Ý nghĩa | v1 | v2 |")
    lines.append("|---|---|---|---|")
    lines.append(f"| Không gợi ý nhầm | không đề xuất dịch vụ vừa bị phủ định "
                 f"| {_pct(ng_v1['no_false_positive'])} | **{_pct(ng_v2['no_false_positive'])}** |")
    lines.append(f"| Đúng hoàn toàn | không gợi ý nhầm **và** vẫn bắt đúng dịch vụ còn lại "
                 f"| {_pct(ng_v1['correct'])} | **{_pct(ng_v2['correct'])}** |")
    lines.append("")
    lines.append("| Câu nhập | Dịch vụ bị phủ định | Engine gợi ý | OK |")
    lines.append("|---|---|---|:--:|")
    for d in ng_v2["detail"]:
        neg = ", ".join(LABEL_NAME.get(c, c) for c in d["negated"]) or "—"
        pred = ", ".join(LABEL_NAME.get(c, c) for c in d["pred"]) or "(không gợi ý gì)"
        lines.append(f"| {d['text']} | {neg} | {pred} | {'✅' if d['ok'] else '❌'} |")
    lines.append("")
    return "\n".join(lines)


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

    ng_rows = load_dataset(NEGATION_PATH)
    ng_v1 = evaluate_negation(ng_rows, "v1")
    ng_v2 = evaluate_negation(ng_rows, "v2")

    ho_v2 = evaluate(load_dataset(HELDOUT_PATH), "v2")

    md = render_markdown(rows, res_v1, res_v2, cx_rows, cx_v2)
    md += "\n" + render_negation_section(ng_v1, ng_v2)
    md += "\n" + render_heldout_section(ho_v2, res_v2)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        f.write(md + "\n")

    # Tóm tắt ra terminal
    print(f"Tập đơn-ý: {res_v2['n']} mẫu, {len(LABELS)} lớp | "
          f"Tập phức tạp: {cx_v2['n']} câu | Tập phủ định: {ng_v2['n']} câu\n")
    print(f"{'Phiên bản':<28}{'Acc@1':>8}{'Acc@2':>8}{'MacroF1':>9}{'ms/câu':>9}")
    for r in (res_v1, res_v2):
        print(f"{r['version']:<28}{_pct(r['accuracy']):>8}{_pct(r['accuracy_top2']):>8}"
              f"{_pct(r['macro_f1']):>9}{r['avg_latency_ms']:>9.3f}")
    print(f"\nTập phức tạp (v2): top-1 chấp nhận {_pct(cx_v2['top1_accept'])}, "
          f"top-2 chấp nhận {_pct(cx_v2['top2_accept'])}, "
          f"top-1 đúng nhãn chính {_pct(cx_v2['top1_exact'])}")
    print(f"Tập phủ định:  v1 không-gợi-ý-nhầm {_pct(ng_v1['no_false_positive'])} | "
          f"v2 {_pct(ng_v2['no_false_positive'])}  (đúng hoàn toàn: v2 {_pct(ng_v2['correct'])})")
    print(f"\n>> HELD-OUT (chưa từng dùng để chỉnh từ khóa): Acc {_pct(ho_v2['accuracy'])}, "
          f"Macro-F1 {_pct(ho_v2['macro_f1'])}")
    print("   (Điểm ở tập đơn-ý phía trên là điểm TRÊN CHÍNH dữ liệu đã tinh chỉnh -> lạc quan.)")
    print(f"\nĐã ghi bảng chi tiết -> {os.path.relpath(RESULTS_PATH, ROOT)}")


if __name__ == "__main__":
    main()
