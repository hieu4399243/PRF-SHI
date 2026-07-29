# Thuyết trình: Đánh giá chất lượng AI — Trợ lý Nha khoa SHI

> Dàn ý phần "Đánh giá chất lượng AI" theo mạch: **Pain point → Mục tiêu → Kết quả**.
> Số liệu lấy từ `eval/results.md`, sinh tự động bởi `eval/evaluate.py` (tái lập được bằng 1 lệnh).

---

## 1. Pain point — nỗi đau xuất phát

Nỗi đau gốc của nghiệp vụ: **bệnh nhân mô tả triệu chứng bằng văn nói tự do, lễ tân phải tự
đoán để xếp vào đúng nhóm dịch vụ** — đoán sai thì bệnh nhân gặp sai bác sĩ. Bot phải làm
thay việc này (triage: câu triệu chứng → 1 trong 9 nhóm dịch vụ nha khoa).

Khi làm thật, nỗi đau lớn vỡ ra thành 4 nỗi đau con — mỗi cái đều có bằng chứng thật:

| # | Pain point | Bằng chứng |
|---|---|---|
| P1 | **Gõ không dấu.** Người Việt chat thường gõ "toi bi sau rang" | Engine v1 (so khớp có dấu) chỉ đạt 72.8% accuracy |
| P2 | **Câu ghép nhiều ý.** "Nhổ răng khôn xong muốn niềng" nhắc 2 dịch vụ cùng lúc | Ép bot chọn 1 đáp án duy nhất là sai đề bài |
| P3 | **Phủ định.** Gõ "tôi *không* bị đau răng" mà bot vẫn mời khám tủy | Bug gốc có thật — trong y tế đây là lỗi nguy hiểm nhất |
| P4 | **Không biết con số nào là thật.** Điểm đo trên chính dữ liệu đã dùng để chỉnh từ khóa là điểm "học thuộc đề" | Cần tập held-out để đo năng lực với câu chưa từng thấy |

---

## 2. Mục tiêu — mỗi pain point → 1 mục tiêu đo được

| # | Mục tiêu | Thước đo | Dataset | Ngưỡng |
|---|---|---|---|---|
| M1 | Phân loại đúng kể cả gõ không dấu | Accuracy top-1, Macro-F1 | `dataset.jsonl` (180 câu, 9 lớp) | ≥ 95% |
| M2 | Câu ghép nhiều ý: gợi ý phải chứa dịch vụ hợp lệ | Top-2 accept | `dataset_complex.jsonl` (40 câu) | ≥ 95% |
| M3 | Tuyệt đối không gợi ý dịch vụ vừa bị phủ định | No-false-positive | `dataset_negation.jsonl` | 100% |
| M4 | Phản hồi tức thì, offline, không tốn phí | Latency trung bình | — | < 50 ms/câu |
| M5 | Hiểu câu diễn giải chưa từng thấy | Accuracy held-out | `dataset_heldout.jsonl` | ~70%+ |

**Điểm ăn tiền cần nhấn:** có **4 bộ dataset riêng biệt**, mỗi bộ đo một năng lực khác nhau
— đa số đồ án chỉ có 1 bộ.

### Chỉ số đo — chú thích dễ hiểu (kèm ví dụ nha khoa)

**Accuracy top-1** — trong 100 câu test, bao nhiêu câu mà **gợi ý ĐẦU TIÊN** của bot
trúng đáp án. Đây là chỉ số "đúng ngay lần đầu".

**Accuracy top-2** — bao nhiêu câu mà đáp án đúng nằm trong **2 gợi ý đầu**. Đo thêm
cái này vì UX thật của bot là *hiện vài gợi ý cho người dùng bấm chọn* — gợi ý thứ 2
đúng thì người dùng vẫn chọn được, trải nghiệm không hỏng.

**Precision (độ chuẩn xác)** — nhìn từ phía *lời bot nói ra*: trong tất cả những lần
bot nói "bạn nên khám **Nha chu**", bao nhiêu lần đúng là Nha chu thật?
→ Precision thấp = bot **báo nhầm** nhiều = phiền bệnh nhân đi sai chỗ.
*Ví dụ: bot nói "Nha chu" 10 lần mà chỉ 7 lần đúng → Precision = 70%.*

**Recall (độ bao phủ)** — nhìn từ phía *thực tế*: trong tất cả những câu thật sự
là bệnh Nha chu, bot **bắt được** bao nhiêu câu?
→ Recall thấp = bot **bỏ sót** nhiều = bệnh nhân cần khám mà bot không nhận ra.
*Ví dụ: có 20 câu Nha chu thật mà bot chỉ nhận ra 15 → Recall = 75%.*

Nhớ nhanh: **Precision = nói ra có đáng tin không · Recall = có bỏ sót không.**
Hai cái kéo co nhau: bot "nói bừa nhiều" thì Recall cao nhưng Precision tụt, bot
"kiệm lời quá" thì ngược lại.

**F1** — gộp Precision và Recall thành 1 con số (trung bình điều hòa). Đặc điểm:
chỉ cao khi **cả hai cùng cao** — một trong hai mà thấp là F1 tụt theo, không "gỡ điểm
trung bình" được. *Ví dụ: Precision 100% nhưng Recall 10% → F1 chỉ ~18%, không phải 55%.*

**Macro (trong Macro-F1)** — cách gộp 9 lớp dịch vụ: tính F1 **riêng từng lớp** rồi lấy
trung bình cộng, mỗi lớp nặng như nhau. Nhờ đó lớp ít mẫu (vd. Nha khoa trẻ em) có
tiếng nói ngang lớp nhiều mẫu — bot không thể "ăn gian" bằng cách chỉ giỏi mấy lớp phổ biến.

**Latency (ms/câu)** — thời gian engine xử lý 1 câu, tính bằng mili-giây. Chatbot cần
phản hồi tức thì; 0.61 ms nghĩa là gần như không tốn thời gian (1 giây = 1000 ms).

**Top-1 / Top-2 accept** (riêng tập câu ghép) — vì câu nhắc 2-3 dịch vụ nên có *nhiều
đáp án hợp lệ* (tập `accept`): "top-1 accept" = gợi ý đầu là MỘT trong các đáp án hợp lệ;
"top-2 accept" = có đáp án hợp lệ trong 2 gợi ý đầu.

**No-false-positive** (riêng tập phủ định) — % câu mà bot **không** gợi ý đúng cái dịch
vụ người dùng vừa phủ định (gõ "không bị đau răng" thì tuyệt đối không được mời khám tủy).

### Ví dụ minh họa — bộ đề mini 10 câu (dùng khi cần giảng lại cho người khác)

Đem 10 câu đi test, trong đó **4 câu thật sự là bệnh Nha chu**. Bot đoán "Nha chu"
tổng cộng **5 lần**: 3 lần trúng, 2 lần trật (2 câu đó thật ra là Trám răng).

| Chỉ số | Phép tính | Nghĩa đời thường |
|---|---|---|
| Precision (Nha chu) | 3/5 = **60%** | Chuông báo cháy kêu 5 lần, chỉ 3 lần cháy thật — 2 lần cả tòa nhà chạy vô ích |
| Recall (Nha chu) | 3/4 = **75%** | Có 4 đám cháy thật, chuông kêu được 3 — **sót 1 đám** (cháy mà chuông im) |
| F1 | 2×0.60×0.75 ÷ 1.35 ≈ **67%** | Nằm giữa nhưng bị kéo về phía số thấp hơn |

Hai kiểu lỗi **đánh đổi nhau**: chỉnh chuông nhạy hơn → hết sót (Recall↑) nhưng kêu nhầm
nhiều (Precision↓); chỉnh lì hơn → ngược lại. F1 ép phải cân cả hai.

### So sánh đời thường cho từng chỉ số

- **Accuracy top-1** = thi trắc nghiệm khoanh 1 đáp án — 180 câu đúng bao nhiêu.
- **Accuracy top-2** = được khoanh 2 đáp án, trúng 1 là ăn điểm. Không phải ăn gian —
  nó mô phỏng đúng UX thật: bot hiện 2 gợi ý dạng nút bấm, gợi ý thứ 2 đúng thì người
  dùng vẫn bấm được, hội thoại không hỏng.
- **F1** = điểm tổng kết có "điểm liệt". Trung bình cộng: P 100% + R 10% → 55% (trông
  vẫn ổn). Trung bình điều hòa (F1): ~18% — một bên gần chết là điểm chết theo, giống
  quy chế thi: một môn 1 điểm thì môn 10 không cứu nổi tổng kết.
- **Macro** = "mỗi tổ một phiếu, không phải mỗi người một phiếu" — F1 tính riêng từng
  lớp rồi chia đều 9 lớp, nên bot không thể học tủ mấy lớp đông mẫu để che việc bỏ bê
  lớp hiếm.
- **Latency ≈ 1 ms** = nhanh hơn một cái chớp mắt (~300 ms) khoảng 300 lần — người dùng
  nhấn Enter là đáp án đã có sẵn, chạy offline nên không tốn phí API.
  *(Lưu ý: latency đo bằng đồng hồ thật nên mỗi lần chạy mỗi khác — 0.6 hay 1.2 ms tùy
  máy bận/rảnh; trên slide ghi "≈ 1 ms" cho an toàn, đừng ghi cứng số lẻ.)*

---

## 3. Kết quả — đạt 4/5 mục tiêu

| Mục tiêu | Kết quả | Đạt? |
|---|---|:--:|
| M1 — không dấu | v2 chuẩn hóa bỏ dấu: 72.8% → **100%** accuracy, Macro-F1 100% | ✅ |
| M2 — câu ghép | Top-2 accept **100%**, top-1 accept 97.5% | ✅ |
| M3 — phủ định | **100%** không gợi ý nhầm — kể cả phân biệt "không" phủ định với "không" câu hỏi (*"có sâu răng không?"*) | ✅ |
| M4 — tốc độ | **0.61 ms/câu**, thuần Python offline, không phí API | ✅ |
| M5 — tổng quát hóa | Held-out chỉ **37.8%** — rule-based mù với câu diễn giải (*"buốt tận óc"*, *"bàn chải dính máu"*) | ❌ |

### Chi tiết đáng kể theo từng mục tiêu

**M1 — eval-driven development.** Đánh giá định lượng cho biết chính xác phải sửa gì
(lỗi tập trung ở câu không dấu), và chứng minh bản sửa có tác dụng (v1 → v2: 72.8% → 100%,
đổi lại latency 0.28 → 0.61 ms/câu — vẫn không đáng kể).

**M2 — đo kiểu "accept set".** Câu "nhổ răng khôn xong muốn niềng" thì trả lời Tiểu phẫu
hay Chỉnh nha đều hợp lệ → mỗi câu có nhãn chính (`label`) + tập dịch vụ hợp lệ (`accept`).
Top-1 đúng nhãn chính chỉ 52.5% nhưng đó không phải thước đo đúng cho UX chatbot gợi ý.

**M3 — cái tinh tế của tiếng Việt.** "Không" đứng *sau* thường là từ để hỏi
(*"có sâu răng không?"*) nên engine chỉ nhìn phủ định đứng trước, không vượt ranh giới
mệnh đề. Đây là ví dụ demo sống rất tốt nếu được phép demo.

**M5 — phân tích lỗi held-out.** Trong 28 câu sai: **22** câu engine *không nhận ra gì*
(hỏng nhẹ — bot hỏi lại), **6** câu *đoán sai dịch vụ* (nguy hiểm hơn — dẫn bệnh nhân
sai bác sĩ).

---

## 4. Cách nói phần kết quả (quan trọng nhất)

Đừng trình bày M5 như thất bại — trình bày nó như **mục tiêu mà hệ thống đánh giá được
xây ra để phát hiện**. Mạch nói gợi ý:

> "Chúng tôi đạt 4/5 mục tiêu. Mục tiêu thứ 5 không đạt — và điều đáng nói là *chính hệ
> thống đánh giá đã được thiết kế để phát hiện ra điều đó*: nếu chỉ đo trên dữ liệu đã
> tinh chỉnh, chúng tôi đã báo cáo 100% và tự tin sai. Tập held-out cho thấy trần của
> rule-based là 37.8%, và phân tích lỗi cho biết 22/28 câu sai là 'không nhận ra'
> (hỏng nhẹ — bot hỏi lại), chỉ 6 câu đoán sai dịch vụ. Đây chính là căn cứ định lượng
> cho bước tiếp theo: cắm LLM vào điểm chờ sẵn `classify_with_llm()`, và bộ eval này sẽ
> dùng nguyên vẹn để đo phiên bản LLM bằng cùng thước đo."

Vòng lặp khép kín: **pain point → mục tiêu đo được → đo → đạt 4/5 → mục tiêu chưa đạt
trở thành roadmap có số liệu chống lưng** — không phải lời hứa suông.

---

## 5. Chuẩn bị câu hỏi phản biện

| Câu hỏi dễ gặp | Cách trả lời |
|---|---|
| "100% có phải overfitting không?" | Chủ động trả lời trước bằng slide held-out — biến điểm yếu thành điểm cộng về phương pháp luận. |
| "Sao không dùng ML/LLM luôn?" | Rule-based cho latency < 1ms, chạy offline không tốn phí, dễ kiểm soát trong ngữ cảnh y tế; và eval đã chứng minh định lượng *lúc nào* cần nâng cấp lên LLM. |
| "F1 là gì / sao dùng macro?" | Xem giải thích ở mục 2. |
| "Kết quả có tái lập được không?" | Toàn bộ số liệu sinh tự động bởi 1 lệnh `python eval/evaluate.py`, ghi ra `eval/results.md`. |

## Mẹo khi nói

- Kể theo mạch **"vấn đề → đo → sửa → đo lại"** thay vì liệt kê bảng số. Người nghe nhớ
  câu chuyện "gõ không dấu làm rớt 27%, sửa xong lên 100%" hơn là nhớ bảng F1.
- Ngưỡng ở mục 2 là tự đặt — chỉnh lại theo đề cương đã cam kết (nếu có) trước khi in slide.
- **Con số cần thuộc lòng** (hội đồng hay hỏi lại đúng số): 72.8 → 100 · 52.5 / 97.5 / 100
  (câu ghép) · 37.8 (held-out) · 22/6 (phân loại lỗi) · 0.61 ms.
- Nếu được demo, chèn demo sống vào phần phủ định: gõ trực tiếp *"tôi không bị đau răng"*
  rồi *"có sâu răng không"* — 10 giây nhưng thuyết phục hơn mọi bảng số.

---

## 6. Lời thoại gợi ý (~4–5 phút)

**Chặng 1 — Pain point (30s)**

> "Phần lõi AI của hệ thống là triage: bệnh nhân gõ một câu mô tả triệu chứng bằng văn nói
> tự do, bot phải xếp vào đúng 1 trong 9 nhóm dịch vụ nha khoa — việc mà bình thường lễ tân
> phải tự đoán, và đoán sai thì bệnh nhân gặp sai bác sĩ. Khi làm thật, chúng tôi phát hiện
> 4 vấn đề cụ thể: một, người Việt chat thường gõ không dấu — 'toi bi sau rang' — và engine
> bản đầu bị mù, chỉ đạt 72.8%. Hai, nhiều câu nhắc 2-3 dịch vụ cùng lúc. Ba, nguy hiểm
> nhất: gõ 'tôi KHÔNG bị đau răng' mà bot vẫn mời khám tủy. Và bốn: chúng tôi không biết
> con số đo được có đáng tin không, vì đo trên chính dữ liệu đã dùng để chỉnh engine thì
> chẳng khác gì học thuộc đề."

**Chặng 2 — Mục tiêu & cách đo (45s)**

> "Từ 4 vấn đề đó, chúng tôi đặt 5 mục tiêu đo được, và xây 4 bộ dataset riêng biệt để đo —
> mỗi bộ đo một năng lực: 180 câu đơn-ý cho độ chính xác cơ bản, 40 câu ghép nhiều ý, một
> bộ câu phủ định, và một bộ held-out gồm câu diễn giải chưa từng dùng để chỉnh engine.
> Chỉ số dùng là Accuracy top-1 và top-2 — đo top-2 vì bot cho người dùng chọn trong vài
> gợi ý — cùng Macro F1 để mọi lớp quan trọng như nhau, và latency. Toàn bộ chạy tự động
> bằng một lệnh, kết quả tái lập được."

**Chặng 3 — Kết quả từng mục tiêu (90s, phần dày nhất)**

> "Kết quả: đạt 4 trên 5 mục tiêu.
>
> Mục tiêu 1 — gõ không dấu: đây là ví dụ điển hình của việc đánh giá dẫn đường cho cải
> tiến. Số liệu chỉ ra lỗi tập trung ở câu không dấu, chúng tôi làm bản v2 chuẩn hóa bỏ
> dấu, chạy lại cùng bộ đo: accuracy từ 72.8% lên 100%, đổi lại latency tăng từ 0.28 lên
> 0.61 mili-giây mỗi câu — không đáng kể.
>
> Mục tiêu 2 — câu ghép nhiều ý: với câu 'nhổ răng khôn xong muốn niềng' thì trả lời Tiểu
> phẫu hay Chỉnh nha đều đúng, nên chúng tôi đo theo tập dịch vụ hợp lệ: top-2 chứa dịch
> vụ hợp lệ đạt 100%.
>
> Mục tiêu 3 — phủ định: đạt 100% không gợi ý nhầm. Điểm thú vị là tiếng Việt: chữ 'không'
> đứng sau thường là câu hỏi — 'có sâu răng không?' — nên engine chỉ xét phủ định đứng
> trước từ khóa, trong cùng mệnh đề.
>
> Mục tiêu 4 — tốc độ: dưới 1 mili-giây, chạy offline, không tốn phí API."

**Chặng 4 — Mục tiêu không đạt & kết (60s, phần ghi điểm nhất)**

> "Mục tiêu thứ 5 không đạt — và đây là phần chúng tôi muốn nhấn mạnh nhất. Nếu chỉ đo
> trên dữ liệu đã tinh chỉnh, chúng tôi đã báo cáo 100% và tự tin sai. Tập held-out cho
> con số trung thực: 37.8%. Rule-based mù hoàn toàn với câu diễn giải — 'buốt tận óc',
> 'bàn chải dính máu'. Phân tích 28 câu sai: 22 câu engine không nhận ra gì — hỏng nhẹ,
> bot chỉ hỏi lại; 6 câu đoán sai dịch vụ — nguy hiểm hơn. Đây chính là trần của
> rule-based, và là căn cứ định lượng cho bước tiếp theo: cắm LLM vào điểm chờ sẵn trong
> kiến trúc, và bộ eval này sẽ dùng nguyên vẹn để đo phiên bản LLM bằng cùng thước đo.
> Tóm lại: pain point → mục tiêu đo được → đạt 4/5 → mục tiêu chưa đạt trở thành roadmap
> có số liệu chống lưng."

Tỷ lệ thời gian: chặng 3–4 chiếm ~60% thời lượng — đó là "kết quả", thứ hội đồng chấm.
Chặng 1–2 nói nhanh, đủ để người nghe hiểu vì sao có 5 mục tiêu.

---

## 7. Hiểu sâu để tự tin trả lời (giải thích thuật ngữ)

### 7.1. "Engine bản đầu (v1) bị mù" nghĩa là gì?

Engine hoạt động bằng **so khớp từ khóa**. V1 lưu từ khóa **có dấu**, ví dụ lớp
"Trám răng" có từ khóa `"sâu răng"`.

- Gõ `"Tôi bị sâu răng"` → v1 tìm thấy chuỗi `"sâu răng"` → nhận ra ✅
- Gõ `"toi bi sau rang"` (không dấu) → v1 đi tìm chuỗi `"sâu răng"` → **không thấy**,
  vì `"sau rang"` ≠ `"sâu răng"` về mặt ký tự → engine trả về "không nhận ra gì" ❌

"Bị mù" là vậy: câu rõ ràng nói về sâu răng nhưng vì lệch dấu nên engine không thấy gì,
như thể câu vô nghĩa. Số câu sai của v1 (27.2%) gần như toàn bộ là câu không dấu.
V2 sửa bằng cách **bỏ dấu cả hai phía trước khi so** (từ khóa lẫn câu nhập đều đưa về
dạng không dấu) nên khớp được.

### 7.2. "Đo trên dữ liệu đã dùng để chỉnh engine = học thuộc đề" nghĩa là gì?

Quy trình làm engine thực tế:

1. Viết bộ từ khóa ban đầu
2. Chạy trên `dataset.jsonl` → thấy câu `"răng lung lay"` bị sai
3. **Thêm từ khóa** `"lung lay"` vào lớp Nha chu → chạy lại → câu đó đúng
4. Lặp cho đến khi cả 180 câu đều đúng → 100%

Con số 100% đó **không chứng minh engine giỏi** — chỉ chứng minh đã thêm đủ từ khóa để
đúng *đúng 180 câu đó*. Giống học sinh được phát trước bộ đề, sai câu nào học thuộc đáp
án câu đó, thi lại chính bộ đề được 10 điểm — điểm 10 không nói lên em ấy hiểu bài.
Câu hỏi thật: **gặp câu MỚI chưa từng thấy, engine làm được bao nhiêu?**

### 7.3. "Bộ held-out gồm câu diễn giải" là gì?

Held-out = **để riêng ra, không đụng tới**. Đây là "bộ đề thi thật":

- ~45 câu người thật có thể gõ, nhưng **cố tình không dùng từ khóa nào** đã có trong
  engine. Cùng nghĩa "sâu răng" nhưng viết *"Uống trà đá là buốt tận óc"*; cùng nghĩa
  "chảy máu nướu" nhưng viết *"Bàn chải luôn dính máu dù chải rất nhẹ"*.
- **Chỉ chạy để chấm, tuyệt đối không dùng để thêm/sửa từ khóa.** Vi phạm là nó thành
  "đề đã học thuộc" và mất giá trị.

Khoảng cách 100% ↔ 37.8% chính là bằng chứng định lượng: rule-based chỉ đúng khi người
dùng *tình cờ gõ trúng* từ khóa, còn muốn hiểu **nghĩa** thì phải dùng LLM.

### 7.4. Held-out được test như thế nào? (cơ chế cụ thể)

**Format dữ liệu** — mỗi dòng `dataset_heldout.jsonl` là cặp `text` (câu người dùng gõ)
+ `label` (nhãn vàng — đáp án đúng do người viết câu gán sẵn):

```json
{"text": "Uống trà đá là buốt tận óc, chắc răng có vấn đề", "label": "sau_rang"}
```

**Quy trình chấm** (`evaluate.py`, dòng 329: `evaluate(load_dataset(HELDOUT_PATH), "v2")`)
— dùng **chung một hàm chấm** với tập 180 câu, chỉ khác nguồn dữ liệu. Với từng câu:

1. **Đưa câu vào engine** y như người dùng gõ vào chatbot:
   `triage.classify_symptoms(text, version="v2")` — engine bỏ dấu, quét từ khóa 9 lớp,
   chấm điểm, trả danh sách lớp theo điểm giảm dần.
2. **Lấy top-1** (lớp điểm cao nhất). Không khớp từ khóa nào → trả rỗng → dự đoán `None`.
3. **So với nhãn vàng**: trùng → đúng; khác hoặc `None` → sai, ghi vào bảng error analysis.

Chạy hết ~45 câu → Accuracy = số đúng / tổng số, cùng Macro-F1 → ra 37.8%.

**Trace 2 câu để thấy vì sao sai:**

- *"Uống trà đá là buốt tận óc"* (nhãn: `sau_rang`) → không từ khóa nào của 9 lớp xuất
  hiện trong câu (từ khóa có "ê buốt" nhưng câu viết "buốt tận óc") → trả rỗng →
  **sai kiểu "không nhận ra"** (22/28 câu sai thuộc loại này — hỏng nhẹ, bot hỏi lại).
- *"rang cua me mot goc nho sau khi can da"* (nhãn: `sau_rang` — răng cửa *mẻ* một góc)
  → chữ `"nho"` không dấu khớp nhầm từ khóa `"nhổ"` của lớp Tiểu phẫu → dự đoán
  `tieu_phau` → **sai kiểu "đoán nhầm lớp"** (6/28 câu — nguy hiểm hơn, dẫn sai bác sĩ).

**Câu trả lời gọn nếu hội đồng hỏi "test held-out như thế nào?":**

> "Cùng một pipeline chấm tự động với tập chính — đưa câu vào engine, so top-1 với nhãn
> vàng gán sẵn — chỉ khác là bộ câu này viết riêng để không trúng từ khóa nào, và chỉ
> dùng để chấm, không bao giờ dùng để chỉnh engine."

---

## 8. Nguồn gốc từng con số trên slide kết quả (tính như nào)

Mọi con số đều là **số câu đạt ÷ tổng số câu** trên từng bộ dataset, do `eval/evaluate.py`
tính tự động. Cụ thể:

| Số trên slide | Phép tính | Ghi chú |
|---|---|---|
| M1: v1 = 72.8% | **131/180** câu top-1 đúng | 49 câu sai gần như toàn bộ là câu không dấu |
| M1: v2 = 100% | **180/180** | Macro-F1 100% vì mỗi lớp đều P=R=F1=100% |
| M2: top-1 accept 97.5% | **39/40** | trượt đúng 1 câu: *"con toi bi sau rang sua va rang moc lech muon nieng"* |
| M2: top-2 accept 100% | **40/40** | câu trượt kia có đáp án hợp lệ ở gợi ý thứ 2 |
| M2: top-1 đúng nhãn chính 52.5% | **21/40** | không phải thước đo chính (câu ghép có nhiều đáp án hợp lệ) |
| M3: 100% | **18/18** câu không gợi ý dịch vụ bị phủ định | chấm bằng phép giao tập hợp |
| M4: ≈ 1 ms/câu | tổng thời gian ÷ 180 câu | **duy nhất số này dao động theo máy** (0.6–1.2 ms) |
| M5: 37.8% | **17/45** câu held-out đúng | 28 câu sai = 22 "không nhận ra" + 6 "đoán nhầm lớp" |

**Lệnh chạy để kiểm chứng** (từ thư mục gốc project, ~2 giây, không cần mạng/API key):

```bash
./.venv/bin/python eval/evaluate.py
```

In tóm tắt ra màn hình + ghi bảng chi tiết vào `eval/results.md`. Nếu demo trực tiếp,
chủ động nói trước: *"riêng thời gian chạy dao động theo máy, các chỉ số chính xác thì
cố định"* — tránh bị bắt bẻ khi latency lệch slide.

**Lưu ý về NGƯỠNG (≥95%, <50ms, ~70%+):** đây là ngưỡng nhóm **tự đặt trước khi đo**
(dựa trên yêu cầu UX chatbot), project không có file nào cam kết sẵn. Nếu hội đồng hỏi
"ngưỡng lấy đâu ra" → trả lời trung thực như vậy; nếu đề cương đã ghi ngưỡng khác thì
sửa slide theo đề cương.

---

## 9. Thuật toán chấm điểm (bên trong `evaluate.py`)

Bản chất là **vòng lặp chấm bài trắc nghiệm** + đếm 3 loại ô. Không có học máy trong
khâu chấm — chỉ đếm và chia, nên kết quả xác định tuyệt đối.

**Tầng 1 — vòng lặp chấm** (hàm `evaluate()`):

```
với TỪNG câu trong dataset:
    1. bấm giờ, đưa câu vào engine → danh sách lớp xếp theo điểm giảm dần
    2. pred = lớp đứng đầu (rỗng thì pred = None)
    3. so pred với nhãn vàng:
         trùng → đếm "đúng", +1 TP của lớp đó
         khác  → +1 FN của lớp đúng (bỏ sót)
                 nếu pred ≠ None: +1 FP của lớp đoán nhầm (báo oan)
```

- **TP** của lớp X = đoán X và đúng là X
- **FP** của lớp X = đoán X nhưng thật ra lớp khác (**báo oan**)
- **FN** của lớp X = thật là X nhưng bot đoán khác/không đoán (**bỏ sót**)

**Tầng 2 — từ 3 bộ đếm ra chỉ số:**

```
Accuracy  = số câu đúng ÷ tổng số câu
Precision = TP ÷ (TP + FP)        Recall = TP ÷ (TP + FN)
F1        = 2·P·R ÷ (P + R)       Macro-F1 = trung bình F1 của 9 lớp
Latency   = tổng thời gian ÷ số câu
```

**Tầng 3 — hai biến thể:**

- Tập câu ghép (`evaluate_complex`): thay so "trùng 1 đáp án" bằng **kiểm tra thuộc tập
  hợp** — pred có nằm trong tập `accept` không (top-1), 1 trong 2 gợi ý đầu có nằm
  trong `accept` không (top-2).
- Tập phủ định (`evaluate_negation`): dùng **phép giao** — (tập bot gợi ý) ∩ (tập bị
  phủ định) ≠ rỗng → SAI.

**Phân biệt quan trọng:** `evaluate.py` là **giám khảo**; engine `app/triage/engine.py` là
**thí sinh**. Thuật toán của thí sinh: mỗi lớp có danh sách từ khóa kèm trọng số → bỏ
dấu câu nhập → từ khóa nào xuất hiện (khớp ranh giới từ, bỏ qua nếu đứng sau từ phủ
định) thì cộng điểm cho lớp → xếp hạng theo tổng điểm.

**Trả lời gọn cho hội đồng:**

> "Thuật toán đánh giá là chấm bài tự động: từng câu đưa vào engine, so gợi ý đầu với
> nhãn vàng, đếm đúng/báo-oan/bỏ-sót cho từng lớp, từ đó suy ra Accuracy, Precision,
> Recall, F1 theo công thức chuẩn của bài toán phân loại. Khâu chấm chỉ là đếm và chia
> nên chạy lại bao nhiêu lần cũng ra đúng một số."

Chi tiết thú vị hay bị hỏi: **vì sao v1 Precision 100% mà F1 chỉ 84.2%?** Vì mọi câu
sai của v1 đều là "không nhận ra" (trả rỗng) chứ không đoán bừa → không có FP nào →
Precision mỗi lớp 100%, nhưng Recall chỉ 72.8% → F1 = 2×1×0.728÷1.728 = 84.2%.

---

## 10. Giải nghĩa các phần dễ gây khó hiểu (Q&A khi soạn bài)

### 10.1. Bảng P1–P4 kể lại kiểu "chuyện gì đã xảy ra"

- **P1 — Gõ không dấu.** Bot nhận diện bằng tìm từ khóa. Từ khóa lưu `"sâu răng"` (có
  dấu), người dùng gõ `"toi bi sau rang"` → máy so ký tự thấy khác nhau → không khớp →
  bot không hiểu. Vì lỗi này v1 chỉ đúng 72.8% — cứ 4 câu sai hơn 1.
- **P2 — Câu ghép.** "Nhổ răng khôn **xong muốn niềng**" nhắc HAI nhu cầu. Nếu cách
  chấm bắt bot trả đúng MỘT đáp án duy nhất thì trả cái nào cũng bị tính sai một nửa —
  trong khi cả hai đều đúng. Vấn đề ở **cách ra đề**, phải cho phép nhiều đáp án hợp lệ.
- **P3 — Phủ định.** Gõ *"tôi không bị đau răng"* → bot chỉ thấy từ khóa "đau răng",
  không hiểu chữ "không" → mời khám tủy — mời đúng cái bệnh người ta vừa nói KHÔNG bị.
- **P4 — Không biết số nào thật.** Quy trình làm bot: chạy test → sai câu nào thêm từ
  khóa câu đó → lặp đến khi 180/180 đúng → 100%. Nhưng đó là "học thuộc đề" — phải có
  bộ đề giấu kín (held-out) mới biết năng lực thật.

Phiên bản bảng slide dễ hiểu hơn (tình huống → hậu quả):

| # | Tình huống thật | Hậu quả nếu không xử lý |
|---|---|---|
| P1 | Gõ không dấu: *"toi bi sau rang"* | Bot không hiểu gì — v1 sai hơn 1/4 số câu (72.8%) |
| P2 | Một câu nhắc 2 dịch vụ: *"nhổ răng khôn xong muốn niềng"* | Ép bot trả 1 đáp án thì kiểu gì cũng "sai" — phải chấm theo nhiều đáp án hợp lệ |
| P3 | *"Tôi **không** bị đau răng"* | Bot thấy chữ "đau răng" vẫn mời khám tủy — ngược ý bệnh nhân |
| P4 | Test mãi trên 180 câu đã dùng để chỉnh bot → 100% | Điểm "học thuộc đề" — gặp câu lạ của bệnh nhân thật là lộ |

Khi nói: đừng đọc bảng — kể mỗi dòng như mẩu chuyện 2 câu ("tình huống là gì → bot làm
sai thế nào").

### 10.2. Vì sao M5 "không đạt" lại là thành công của hệ đánh giá — chuỗi 4 bước

1. **"Nếu chỉ đo trên dữ liệu đã tinh chỉnh, ta báo cáo 100% và tự tin sai."** Không có
   held-out thì toàn bộ số liệu là 100% → lên thuyết trình nói "đúng 100%" và TIN thật.
   Nhưng ngày mai bệnh nhân gõ *"uống trà đá buốt tận óc"* là bot đứng hình — và ta
   không hề biết trước. "Tự tin sai" = con số đẹp làm ta tưởng hệ thống tốt hơn thực tế.
2. **"Trần rule-based là 37.8%."** "Trần" (ceiling) = không sửa được bằng cách cố thêm.
   Vá từ khóa "buốt tận óc" thì mai người khác gõ "ê ẩm cả hàm", "nhức lên thái dương"…
   Tiếng Việt có vô hạn cách diễn đạt, bộ từ khóa hữu hạn không đuổi kịp → ~38% là giới
   hạn của cả PHƯƠNG PHÁP, không phải của phiên bản hiện tại.
3. **"22/28 không nhận ra (hỏng nhẹ), 6 đoán sai."** Hai kiểu sai hậu quả khác hẳn:
   không nhận ra → bot hỏi lại → phiền nhưng không ai bị hại; đoán sai → đặt lịch SAI
   bác sĩ → hậu quả thật. Phần lớn cái sai thuộc loại vô hại → hệ thống **sai theo kiểu
   an toàn** (fail-safe) — điểm gỡ lại cho con số 37.8% trông thấp.
4. **"Căn cứ định lượng để cắm LLM."** = lý do nâng cấp có số chống lưng, không cảm
   tính. So sánh: *"em nghĩ nên dùng LLM cho xịn"* (bị hỏi: tốt hơn bao nhiêu? — tịt)
   vs *"rule-based kịch trần 37.8% với câu diễn giải, muốn vượt phải hiểu NGHĨA thay vì
   khớp CHỮ → cần LLM; cắm vào `classify_with_llm()` rồi chạy lại đúng bộ held-out này
   — LLM đạt ví dụ 85% là có bằng chứng nâng cấp đáng giá."* Bộ held-out trở thành
   **thước đo chuẩn** cho mọi phiên bản tương lai — cùng một đề thi mới so công bằng.

Tóm một câu: *Không có held-out → báo cáo 100% và bị bất ngờ khi chạy thật. Có held-out
→ biết trước năng lực thật 37.8%, biết sai chủ yếu kiểu vô hại, biết chính xác vì sao +
khi nào cần LLM.* → M5 "không đạt" là thành công của HỆ ĐÁNH GIÁ: nó được xây ra chính
để phát hiện điều này. Đạt 4/5 mà nói được vậy ghi điểm hơn "đạt 5/5".

### 10.3. Macro-F1 — ví dụ 3 lớp cho thấy vì sao công bằng

| Lớp | Số câu test | F1 |
|---|---|---|
| Trám răng | 100 | 95% |
| Nội nha | 100 | 95% |
| Nha khoa trẻ em | 10 | **20%** (bot rất kém lớp này) |

- Gộp theo *số câu*: lớp trẻ em chỉ 10/210 câu nên điểm kém bị **nhấn chìm** → tổng vẫn
  ~91%, che mất việc bot hỏng hẳn một mảng.
- **Macro**: (95+95+20) ÷ 3 = **70%** → tụt rõ, lộ ngay lớp đang hỏng.

→ Macro chống "học tủ": bệnh nhi tuy ít nhưng vẫn phải được phân loại đúng như người lớn.

Trả lời 1 hơi: *"F1 là điểm cân bằng giữa báo-nhầm và bỏ-sót của một lớp; Macro-F1 là
trung bình cộng F1 của 9 lớp, mỗi lớp nặng như nhau — để lớp ít mẫu không bị lớp đông
mẫu che khuất."*

### 10.4. "Nha chu" là gì (từ chuyên môn hay bị hỏi)

Chuyên khoa về **nướu (lợi) và mô quanh răng** — phần "nền móng" giữ răng, không phải
bản thân cái răng (*nha* = răng, *chu* = xung quanh). Triệu chứng thuộc lớp này: chảy
máu chân răng, nướu sưng/viêm lợi, hôi miệng, răng lung lay do nền nướu yếu.

| Triệu chứng | Thuộc lớp |
|---|---|
| Chảy máu nướu, viêm lợi, hôi miệng | **Nha chu** |
| Lỗ sâu, ê buốt | Trám răng / Sâu răng |
| Đau nhức dữ dội tận tủy | Nội nha (Điều trị tủy) |

### 10.5. Chú thích cột "Thước đo" cho slide

Mỗi thước đo một dòng footnote:

| Thước đo | Chú thích trên slide |
|---|---|
| Accuracy top-1 | % câu mà gợi ý đầu tiên của bot đúng |
| Accuracy top-2 | % câu có đáp án đúng trong 2 gợi ý đầu (bot cho người dùng chọn) |
| Macro-F1 | điểm cân bằng "báo nhầm"–"bỏ sót", tính đều cho 9 lớp |
| Top-2 accept | % câu có ≥1 dịch vụ hợp lệ trong 2 gợi ý đầu (câu ghép nhiều đáp án đúng) |
| No-false-positive | % câu KHÔNG gợi ý dịch vụ người dùng vừa phủ định |
| Latency | thời gian xử lý 1 câu (mili-giây) |
| Accuracy held-out | accuracy trên bộ câu chưa từng dùng chỉnh engine — năng lực thật |

Hoặc (khuyên dùng) thêm thẳng cột "Nghĩa là" vào bảng mục tiêu:

| # | Mục tiêu | Thước đo | Nghĩa là | Ngưỡng |
|---|---|---|---|---|
| M1 | Đúng kể cả gõ không dấu | Accuracy top-1 | gợi ý đầu tiên đúng bao nhiêu % | ≥ 95% |
| M2 | Câu ghép: gợi ý chứa dịch vụ hợp lệ | Top-2 accept | 1 trong 2 gợi ý đầu là đáp án hợp lệ | ≥ 95% |
| M3 | Không gợi ý cái vừa bị phủ định | No-false-positive | "không bị đau răng" → không mời khám tủy | 100% |
| M4 | Phản hồi tức thì, offline | Latency | thời gian xử lý 1 câu | < 50 ms |
| M5 | Hiểu câu diễn giải chưa từng thấy | Accuracy held-out | đo trên bộ đề "giấu kín" chưa dùng chỉnh engine | ~70%+ |
