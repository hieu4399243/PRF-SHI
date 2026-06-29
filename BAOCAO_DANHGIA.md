# Báo cáo đánh giá hệ thống AI — Trợ lý Nha khoa SHI

Đề tài: Chatbot tiếng Việt giúp **chọn đúng dịch vụ nha khoa** từ mô tả triệu chứng
và **đặt lịch hẹn**. Tài liệu này trình bày phần đánh giá thành phần AI (triage engine)
theo luồng: *Mục đích → Mục tiêu → Cách đánh giá → Kết quả → Kết luận*.

> Số liệu trong báo cáo được sinh tự động bởi `eval/evaluate.py` (xem `eval/results.md`).
> Chạy lại: `./.venv/bin/python eval/evaluate.py`

---

## 1. Mục đích của việc ứng dụng AI

Phòng khám Nha khoa SHI có 9 nhóm dịch vụ (Khám tổng quát/Cạo vôi, Trám răng/Sâu răng,
Nội nha, Nha chu, Nhổ răng/Tiểu phẫu, Chỉnh nha, Phục hình/Trồng răng, Thẩm mỹ, Nha nhi).
Người bệnh thường **không biết mình nên đăng ký dịch vụ nào**, mô tả bằng ngôn ngữ đời
thường (và hay **gõ thiếu dấu**).

Thành phần AI (**triage engine**) có nhiệm vụ: *từ mô tả triệu chứng tiếng Việt →
phân loại đúng nhóm dịch vụ nha khoa*, để:
- Giảm thời gian/thao tác cho người bệnh và lễ tân.
- Định tuyến đúng bác sĩ phụ trách ngay từ đầu.
- Làm nền cho bước đặt lịch tự động.

## 2. Mục tiêu cần đạt (cụ thể bằng con số)

| Mục tiêu | Chỉ số | Ngưỡng đặt ra |
|---|---|---|
| Phân loại đúng dịch vụ | Accuracy | **≥ 90%** |
| Cân bằng giữa các lớp | Macro-F1 | **≥ 0.90** |
| Hiểu cả tiếng Việt không dấu | Accuracy trên mẫu không dấu | **≥ 85%** |
| Phản hồi nhanh (trải nghiệm chat) | Thời gian xử lý/câu | **< 50 ms** |
| Chi phí vận hành | Chi phí/1.000 lượt | **= 0đ** (rule-based, không gọi API) |
| Chất lượng hội thoại (định tính) | Điểm rubric trung bình | **≥ 4.0/5** |

## 3. Cách thức đánh giá

### 3.1. Phương pháp định lượng
- **Bộ dữ liệu (dataset):** `eval/dataset.jsonl` — **63 câu** mô tả triệu chứng có gán
  nhãn dịch vụ đúng, **7 câu/lớp × 9 lớp** (cân bằng). Trong đó cố ý đưa ~**18 câu gõ
  thiếu dấu** (vd. *"toi muon nieng rang"*) để kiểm tra khả năng chịu lỗi chính tả.
- **Phương pháp:** so dự đoán **top-1** của engine với nhãn vàng; tính **Precision,
  Recall, F1** cho từng lớp, **Macro-average**, **Accuracy** tổng thể và **thời gian
  trung bình** mỗi câu.
- **Công thức:**
  - Precision = TP / (TP + FP)
  - Recall = TP / (TP + FN)
  - F1 = 2·Precision·Recall / (Precision + Recall)
  - Macro-F1 = trung bình F1 của 9 lớp
- **So sánh 2 phiên bản engine:**
  - **v1** — khớp từ khóa có dấu, theo ranh giới từ.
  - **v2** — như v1 nhưng **không phân biệt dấu** (accent-insensitive) → bắt được
    cả khi người dùng gõ thiếu dấu.

### 3.2. Phương pháp định tính
- Rubric 6 tiêu chí (Đúng dịch vụ, An toàn, Robustness, Hoàn tất tác vụ, Tự nhiên,
  Quyền riêng tư), chấm thang 1–5 trên bộ kịch bản mẫu — xem `eval/rubric.md`.

## 4. Kết quả đánh giá

### 4.1. So sánh tổng thể (định lượng)

| Chỉ số | v1 (có dấu) | v2 (không phân biệt dấu) | Mục tiêu |
|---|---|---|---|
| Accuracy | 77.8% | **100.0%** | ≥ 90% ✅ |
| Macro Precision | 100.0% | 100.0% | — |
| Macro Recall | 77.8% | 100.0% | — |
| Macro F1 | 87.3% | **100.0%** | ≥ 0.90 ✅ |
| Thời gian TB | 0.05 ms | **0.25 ms** | < 50 ms ✅ |
| Chi phí | 0đ | 0đ | 0đ ✅ |

> v1 đạt Precision cao (khi nhận ra thì gần như đúng) nhưng **Recall thấp**: bỏ sót
> toàn bộ câu gõ thiếu dấu (trả "không nhận ra"). v2 khắc phục điểm này.
>
> ⚠️ **Lưu ý trung thực:** v2 đạt 100% trên tập 63 câu này, nhưng bộ từ khóa đã được
> hiệu chỉnh **dựa trên chính tập này** (chưa tách tập test riêng). Con số 100% vì vậy
> phản ánh độ khớp trên dữ liệu phát triển, **không nên hiểu là độ chính xác thực tế**.
> Xem mục Hướng phát triển về việc cần một tập test độc lập.

### 4.2. F1 theo từng dịch vụ (v2)

Trên tập hiện tại, cả 9 lớp đạt F1 = 100% (chi tiết trong `eval/results.md`). Trước khi
hiệu chỉnh, các lỗi điển hình là: câu gõ thiếu dấu (v1 bỏ sót), cách diễn đạt lạ
(*"bị mẻ"* vs *"răng mẻ"*), và nhập nhằng Nha nhi vs Sâu răng (khi câu vừa nhắc "trẻ"
vừa "đau răng") — đã xử lý bằng cách bổ sung từ khóa & ưu tiên tín hiệu trẻ em.

### 4.3. Định tính
Trên bộ kịch bản `eval/rubric.md`, hệ thống xử lý đúng các tình huống an toàn
(cấp cứu → 115, từ chối chẩn đoán/kê đơn, human handoff) và ẩn PII trong `audit_log.jsonl`.

## 5. Kết luận

- **Phiên bản tốt nhất: v2** (accent-insensitive + khớp theo ranh giới từ) — vượt mục
  tiêu: Accuracy 100% (trên tập dev), Macro-F1 1.0, < 1 ms/câu, chi phí 0đ. Đây là phiên
  bản đang dùng trong sản phẩm (`triage.DEFAULT_VERSION = "v2"`).
- **Khó khăn / tồn tại:**
  1. Bản chất **rule-based theo từ khóa** → phải bổ sung từ khóa thủ công cho mỗi cách
     nói mới; khó phủ hết biến thể ngôn ngữ (đồng nghĩa, nói vòng).
  2. **Chưa có tập test độc lập:** từ khóa được hiệu chỉnh trên chính tập 63 câu → điểm
     100% là trên dữ liệu phát triển, dễ **lạc quan hơn thực tế**.
  3. Triệu chứng mơ hồ (vd *"đau răng"*) vốn thuộc nhiều dịch vụ → engine để **medium
     confidence** và đưa 2–3 lựa chọn cho người dùng; top-1 accuracy không phản ánh hết
     trải nghiệm này.
- **Hướng phát triển:**
  1. Mở rộng dataset (≥ 300 câu, có tập **test riêng** để đo khả năng tổng quát hóa).
  2. Bổ sung từ điển đồng nghĩa, hoặc nâng cấp NLU bằng **LLM (Claude)** qua
     `triage.classify_with_llm()` rồi đánh giá lại bằng đúng quy trình này (thêm cột
     "v3 = LLM" vào bảng so sánh) — cân nhắc trade-off độ chính xác vs chi phí/độ trễ.
  3. Thêm đánh giá top-2/top-3 accuracy (vì bot vốn cho người dùng chọn trong vài gợi ý).
