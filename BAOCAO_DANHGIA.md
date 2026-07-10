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
| Phân loại đúng dịch vụ | Accuracy (top-1) | **≥ 90%** |
| Cân bằng giữa các lớp | Macro-F1 | **≥ 0.90** |
| Gợi ý đúng trong vài lựa chọn | Accuracy (top-2) | **≥ 95%** |
| Hiểu cả tiếng Việt không dấu | Accuracy trên mẫu không dấu | **≥ 85%** |
| Xử lý câu **ghép nhiều ý** | Top-2 chấp nhận được | **≥ 90%** |
| Phản hồi nhanh (trải nghiệm chat) | Thời gian xử lý/câu | **< 50 ms** |
| Chi phí vận hành | Chi phí/1.000 lượt | **= 0đ** (rule-based, không gọi API) |
| Chất lượng hội thoại (định tính) | Điểm rubric trung bình | **≥ 4.0/5** |

## 3. Cách thức đánh giá

### 3.1. Quy trình chấm điểm tự động

Việc đánh giá được **tự động hóa hoàn toàn** trong thư mục `eval/`, gồm 3 thành phần:

| Thành phần | Vai trò |
|---|---|
| `dataset.jsonl`, `dataset_complex.jsonl` | **Đề + đáp án**: mỗi dòng là 1 câu mô tả kèm nhãn dịch vụ đúng |
| `evaluate.py` | **Bộ chấm**: cho engine đoán từng câu, so với đáp án, tính chỉ số |
| `results.md` | **Bảng điểm** sinh tự động (không sửa tay — chạy lại là ghi đè) |

Luồng chạy khi gõ `./.venv/bin/python eval/evaluate.py`:

```
dataset.jsonl ──► với mỗi câu: triage.classify_symptoms(text) ──► danh sách dịch vụ xếp theo điểm
        │                                                                    │
        │              so dự đoán (top-1 / top-2) với nhãn đáp án            ▼
        └────────────► cộng dồn đúng/sai theo lớp ──► tính Accuracy, P/R/F1 ──► ghi results.md
                       (làm cho cả v1 và v2 để so sánh)
```

**Ví dụ một câu:** dòng `{"text": "toi muon nieng rang", "label": "chinh_nha"}` → engine đoán
`chinh_nha` → **đúng** → cộng 1 cho lớp Chỉnh nha. Nếu đoán sai, câu đó được ghi vào bảng
"phân tích lỗi" (mục 4.3) để biết engine nhầm ở đâu.

Ưu điểm: **đo lại bất cứ lúc nào chỉ bằng 1 lệnh** — sửa từ khóa trong `triage.py` rồi chạy lại
là biết ngay tốt lên hay tệ đi (không cần đánh giá thủ công).

### 3.2. Dữ liệu đánh giá (hai tập)

Để trả lời góp ý "tập test còn ít, cần câu phức tạp/đa dạng hơn", nhóm dùng **hai tập**:

**(a) Tập câu ĐƠN-Ý** — `eval/dataset.jsonl`: **90 câu** mô tả triệu chứng, mỗi câu ứng với
**đúng 1 dịch vụ**, cân bằng **10 câu/lớp × 9 lớp**. Trong đó cố ý đưa:
- ~**25 câu gõ thiếu dấu** (vd. *"toi muon nieng rang"*) để kiểm tra khả năng chịu lỗi chính tả;
- nhiều câu **khẩu ngữ/nói vòng** (vd. *"Ăn kẹo xong thấy nhói một chiếc răng"*) để tập không
  "quá dễ" với bộ từ khóa.

**(b) Tập câu PHỨC TẠP** — `eval/dataset_complex.jsonl`: **20 câu ghép 2-3 ý** trong một câu
(vd. *"Răng khôn mọc lệch đau quá, nhổ xong tôi muốn niềng cho đều"* nhắc **cả nhổ răng lẫn
chỉnh nha**). Mỗi câu có:
- `label` — dịch vụ **chính** (ưu tiên định tuyến);
- `accept` — **tập mọi dịch vụ hợp lệ** được nhắc tới.

### 3.3. Phương pháp định lượng

**Với tập đơn-ý:** so dự đoán của engine với nhãn vàng, tính **Precision, Recall, F1** cho
từng lớp, **Macro-average**, **Accuracy** và **thời gian trung bình** mỗi câu. Đo cả:
- **Accuracy top-1** — dự đoán hạng 1 đúng nhãn;
- **Accuracy top-2** — nhãn đúng nằm trong 2 gợi ý đầu (vì chatbot cho người dùng chọn trong
  vài gợi ý khi độ tin cậy chưa cao).

**Với tập phức tạp:** một câu nhắc nhiều dịch vụ nên "top-1 đúng nhãn chính" là chưa đủ; nhóm
đo thêm hai chỉ số sát trải nghiệm thực:
- **Top-1 chấp nhận được** — top-1 rơi vào **một** dịch vụ hợp lệ (`accept`);
- **Top-2 chấp nhận được** — có **ít nhất một** dịch vụ hợp lệ trong 2 gợi ý đầu.

**Công thức (tập đơn-ý):**
- Precision = TP / (TP + FP); Recall = TP / (TP + FN)
- F1 = 2·P·R / (P + R); Macro-F1 = trung bình F1 của 9 lớp

**So sánh 2 phiên bản engine:** **v1** (khớp có dấu) vs **v2** (không phân biệt dấu → bắt cả
câu thiếu dấu).

### 3.4. Phương pháp định tính
Rubric 6 tiêu chí (Đúng dịch vụ, An toàn, Robustness, Hoàn tất tác vụ, Tự nhiên, Quyền riêng
tư), chấm thang 1–5 trên bộ kịch bản mẫu — xem `eval/rubric.md`.

## 4. Kết quả đánh giá

### 4.1. So sánh tổng thể — tập đơn-ý (định lượng)

| Chỉ số | v1 (có dấu) | v2 (không phân biệt dấu) | Mục tiêu |
|---|---|---|---|
| Accuracy (top-1) | 73.3% | **97.8%** | ≥ 90% ✅ |
| Accuracy (top-2) | 74.4% | **98.9%** | ≥ 95% ✅ |
| Macro Precision | 98.6% | 99.0% | — |
| Macro Recall | 73.3% | **97.8%** | — |
| Macro F1 | 83.9% | **98.3%** | ≥ 0.90 ✅ |
| Thời gian TB | 0.07 ms | **0.18 ms** | < 50 ms ✅ |
| Chi phí | 0đ | 0đ | 0đ ✅ |

> v1 đạt Precision cao (khi nhận ra thì gần như đúng) nhưng **Recall thấp**: bỏ sót phần lớn
> câu gõ thiếu dấu (trả "không nhận ra"). v2 khắc phục điểm này, tăng Accuracy top-1 từ 73.3%
> lên 97.8% — chứng minh **xử lý không dấu là cải tiến then chốt**.
>
> ⚠️ **Lưu ý trung thực:** bộ từ khóa được hiệu chỉnh **dựa trên chính tập phát triển này**
> (chưa tách tập test riêng). Con số 97.8% phản ánh độ khớp trên dữ liệu phát triển, **không
> nên hiểu là độ chính xác thực tế**. Xem mục Hướng phát triển về việc cần một tập test độc lập.

### 4.2. F1 theo từng dịch vụ (v2, tập đơn-ý)

Đa số lớp đạt F1 = 100%; ba lớp còn lỗi lẻ (chi tiết trong `eval/results.md`):

| Dịch vụ | Precision | Recall | F1 |
|---|---|---|---|
| Trám răng / Sâu răng | 90.9% | 100.0% | 95.2% |
| Phục hình / Trồng răng | 100.0% | 90.0% | 94.7% |
| Nha khoa trẻ em | 100.0% | 90.0% | 94.7% |
| *(6 lớp còn lại)* | 100.0% | 100.0% | 100.0% |

### 4.3. Phân tích lỗi (error analysis, tập đơn-ý)

Chỉ **2/90 câu** sai — và đều nằm ở các "vùng mờ" đã biết:

| Câu nhập | Nhãn đúng | Dự đoán | Nguyên nhân |
|---|---|---|---|
| "Muốn làm **cầu răng sứ** cho chỗ **răng đã mất**" | Phục hình / Trồng răng | (không nhận ra) | Thiếu từ khóa "cầu răng sứ"; "răng đã mất" không khớp trọn từ "mất răng". |
| "**Bé** 6 tuổi bị **sâu răng sữa** nhiều cái" | Nha khoa trẻ em | Trám răng / Sâu răng | Tín hiệu trẻ em ("bé") và sâu răng cùng xuất hiện → điểm nghiêng về Sâu răng. |

Cả hai lỗi khớp đúng **hạn chế cố hữu của rule-based**: phụ thuộc bộ từ khóa và ranh giới
**Nha nhi ↔ Sâu răng**. Hướng khắc phục: bổ sung từ khóa ("cầu răng sứ") và **ưu tiên tín
hiệu trẻ em** khi câu có cả "bé/con" lẫn triệu chứng chung.

### 4.4. Kết quả trên tập câu PHỨC TẠP (ghép 2-3 ý)

| Chỉ số | Ý nghĩa | Kết quả (v2) | Mục tiêu |
|---|---|---|---|
| Top-1 đúng nhãn chính | top-1 == dịch vụ chính | 55.0% | — |
| Top-1 chấp nhận được | top-1 là một dịch vụ hợp lệ | **90.0%** | — |
| Top-2 chấp nhận được | có dịch vụ hợp lệ trong top-2 | **100.0%** | ≥ 90% ✅ |

**Diễn giải.** Với câu ghép nhiều ý, "top-1 đúng nhãn chính" thấp (55%) là **hợp lý**: khi
người dùng nói cùng lúc *"nhổ răng khôn"* và *"niềng cho đều"*, việc engine chọn "nhổ răng" hay
"chỉnh nha" làm hạng 1 đều **không sai** — cả hai đều là dịch vụ đúng. Vì thế hai chỉ số phù hợp
hơn là **top-1 chấp nhận được (90%)** và **top-2 chấp nhận được (100%)**: engine **luôn** đưa ít
nhất một dịch vụ đúng vào 2 gợi ý đầu. Điều này khớp đúng thiết kế hội thoại: khi câu mơ hồ/đa ý,
bot để **medium confidence** và **hiển thị 2–3 lựa chọn** cho người dùng chốt, thay vì đoán cứng.

Hai câu top-1 chưa "chấp nhận được" đều rơi vào ranh giới **Nha nhi ↔ Sâu răng** (câu vừa nhắc
"con/bé" vừa "sâu răng") — cùng nguyên nhân với mục 4.3, nhưng **top-2 vẫn cứu đúng**.

### 4.5. Định tính
Trên bộ kịch bản `eval/rubric.md`, hệ thống xử lý đúng các tình huống an toàn (cấp cứu → 115,
từ chối chẩn đoán/kê đơn, human handoff) và ẩn PII trong `app/audit_log.jsonl`.

### 4.6. Năng lực NLU bổ sung (định tính)
Ngoài phân loại top-1, engine còn có **fallback than phiền chung** (`mentions_dental_discomfort`)
và **hỏi–đáp thông tin dịch vụ** (`info_question_service`). Đây là bổ sung định tính, đo định
lượng riêng được để trong Hướng phát triển (cần tập gán nhãn intent riêng).

## 5. Kết luận

- **Phiên bản tốt nhất: v2** (accent-insensitive + khớp theo ranh giới từ) — đạt/vượt mục tiêu:
  Accuracy top-1 97.8%, top-2 98.9%, Macro-F1 0.983, < 1 ms/câu, chi phí 0đ. Trên câu ghép
  nhiều ý, **top-2 chấp nhận được 100%**. Đây là phiên bản đang dùng trong sản phẩm
  (`triage.DEFAULT_VERSION = "v2"`).
- **Khó khăn / tồn tại:**
  1. Bản chất **rule-based theo từ khóa** → phải bổ sung từ khóa thủ công cho mỗi cách nói mới;
     khó phủ hết biến thể ngôn ngữ (thấy rõ ở 2 lỗi mục 4.3).
  2. **Chưa có tập test độc lập:** từ khóa hiệu chỉnh trên chính tập phát triển → số liệu dễ
     lạc quan hơn thực tế.
  3. Ranh giới **Nha nhi ↔ Sâu răng** và câu ghép nhiều ý cần top-2/hội thoại xác nhận, không
     nên chỉ nhìn top-1.
- **Hướng phát triển:**
  1. Mở rộng dataset (≥ 300 câu, có tập **test riêng** để đo khả năng tổng quát hóa).
  2. Bổ sung từ điển đồng nghĩa, hoặc nâng cấp NLU bằng **LLM (Claude)** qua
     `triage.classify_with_llm()` rồi đánh giá lại bằng đúng quy trình này (thêm cột "v3 = LLM").
  3. Ưu tiên tín hiệu trẻ em để gỡ ranh giới Nha nhi ↔ Sâu răng; bổ sung từ khóa còn thiếu.
  4. Gán nhãn tập riêng cho **intent** (hỏi thông tin dịch vụ, than phiền chung, hủy lịch) để đo
     định lượng các năng lực NLU ở mục 4.6.
