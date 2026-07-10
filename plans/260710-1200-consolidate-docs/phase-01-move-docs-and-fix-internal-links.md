---
phase: 1
title: "Move Docs And Fix Internal Links"
status: completed
priority: P1
dependencies: []
---

# Phase 1: Dời file vào `docs/`, sửa link nội bộ, sửa path code, xoá file thừa

## Overview

Phase NỀN TẢNG — Phase 2, 3 phụ thuộc cấu trúc này đã tồn tại. `git mv` toàn bộ file mục
tiêu vào `docs/`, sửa TOÀN BỘ link markdown NẰM BÊN TRONG các file vừa dời (độ sâu tương đối
thay đổi khi dời thư mục), sửa `eval/evaluate.py`'s `RESULTS_PATH`, xoá 2 file không dùng.

## Requirements

- Functional: `docs/hoc/*.md` (10 file), `docs/eval/rubric.md`, `docs/eval/results.md`,
  `docs/BAOCAO_DOAN.md`, `docs/BAOCAO_DANHGIA.md` tồn tại đúng vị trí. Mọi link markdown BÊN
  TRONG các file này (trỏ ra ngoài, hoặc trỏ tới nhau) phải resolve đúng sau khi dời.
  `eval/evaluate.py` ghi kết quả vào `docs/eval/results.md`.
- Non-functional: Dùng `git mv` (giữ lịch sử). KHÔNG viết lại nội dung — chỉ sửa
  đường dẫn/link. `README.md` gốc, `plans/*.md`, `mobile/README.md` KHÔNG bị đụng.

## Architecture

### Bước 1 — `git mv`
`[Red team — Accept, Finding "git mv eval/results.md assumes tracked, no precheck"]`
`eval/results.md` là file DO `evaluate.py` TỰ SINH — kiểm tra đã được git track trước khi
`git mv` (nếu chưa track, `git mv` sẽ báo lỗi "not under version control"):
```bash
git ls-files --error-unmatch eval/results.md
```
Nếu lệnh trên báo lỗi (file chưa track), dùng `mv` thường + `git add` thay vì `git mv` cho
riêng file này (không có lịch sử để giữ).
```bash
mkdir -p docs/hoc docs/eval
git mv hoc/00-muc-luc.md hoc/01-viet-triage-tu-dau.md hoc/02-data.md hoc/03-safety.md \
       hoc/04-booking.md hoc/05-push.md hoc/06-chatbot.md hoc/07-app.md \
       hoc/08-storage-calendar-reminder.md hoc/09-admin.md docs/hoc/
git mv eval/rubric.md docs/eval/rubric.md
git mv eval/results.md docs/eval/results.md
git mv BAOCAO_DOAN.md docs/BAOCAO_DOAN.md
git mv BAOCAO_DANHGIA.md docs/BAOCAO_DANHGIA.md
```
Sau bước này, thư mục `hoc/` (gốc) trống — xoá luôn (`rmdir hoc` hoặc để git tự dọn nếu
không còn file nào). `eval/` (gốc) VẪN CÒN `evaluate.py`, `dataset.jsonl`,
`dataset_complex.jsonl` — không xoá thư mục `eval/`.

### Bước 2 — sửa `eval/evaluate.py` (RỦI RO KỸ THUẬT ẨN, xem plan.md)
```python
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "results.md")
```
đổi thành (đường dẫn TUYỆT ĐỐI tới vị trí mới, không dùng `os.path.dirname(__file__)` nữa
cho hằng số NÀY — vì file kết quả không còn nằm cạnh script sinh ra nó):
```python
RESULTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # ROOT
    "docs", "eval", "results.md",
)
```
Đọc lại `eval/evaluate.py` để xác nhận có sẵn biến `ROOT`/tương tự chưa (file này ĐÃ có
`ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` dùng cho
`sys.path.insert` — TÁI SỬ DỤNG biến `ROOT` có sẵn thay vì viết lại logic tương tự, đúng
DRY):
```python
RESULTS_PATH = os.path.join(ROOT, "docs", "eval", "results.md")
```
Đọc kỹ dòng docstring đầu file (`Kết quả in ra màn hình và ghi vào eval/results.md`) và dòng
`print(f"\nĐã ghi bảng chi tiết -> {os.path.relpath(RESULTS_PATH, ROOT)}")` — CẢ 2 chỗ này
tự động in đúng đường dẫn tương đối mới nếu `RESULTS_PATH` đã sửa đúng (dòng print dùng
`os.path.relpath`, không cần sửa thêm), nhưng docstring PROSE ở đầu file ghi cứng
`eval/results.md` — sửa thành `docs/eval/results.md` cho khớp.

### Bước 3 — sửa link nội bộ trong 6 bài `hoc/*.md` trỏ tới `app/*.py`
Đọc CHÍNH XÁC từng dòng (đã xác nhận qua grep trước khi viết plan, số dòng có thể lệch):
- `docs/hoc/01-viet-triage-tu-dau.md`: `[triage.py](../app/triage.py)` →
  `[triage.py](../../app/triage.py)`
- `docs/hoc/02-data.md`: `[data.py](../app/data.py)` → `[data.py](../../app/data.py)`
- `docs/hoc/04-booking.md`: `[booking.py](../app/booking.py)` →
  `[booking.py](../../app/booking.py)`
- `docs/hoc/05-push.md`: `[push.py](../app/push.py)` → `[push.py](../../app/push.py)`
- `docs/hoc/06-chatbot.md`: `[chatbot.py](../app/chatbot.py)` →
  `[chatbot.py](../../app/chatbot.py)`
- `docs/hoc/07-app.md`: `[app.py](../app/app.py)` → `[app.py](../../app/app.py)`

### Bước 4 — sửa link trong `docs/hoc/08-storage-calendar-reminder.md`
```
[DATABASE.md](../docs/database-storage-guide.md)
```
đổi thành (target giờ là ANH EM cùng cấp `docs/`, không cần đi qua `docs/` nữa vì bản thân
file này đã Ở TRONG `docs/hoc/`):
```
[DATABASE.md](../database-storage-guide.md)
```

### Bước 5 — xoá file thừa
`[Red team — Accept, Finding "release-manifest.json vs .repomixignore deletion scope"]`
CHỈ xoá `release-manifest.json` — `.repomixignore` GIỮ NGUYÊN (quyết định đảo ngược sau
red-team: `.claude/agents/docs-manager.md`, `.claude/agents/debugger.md` gọi `repomix` trực
tiếp và dựa vào file này để loại trừ `docs/*`, `plans/*`, `tests/*` — xoá sẽ khiến lần chạy
`repomix` tiếp theo nuốt nhầm các thư mục này vào manifest).
```bash
git rm release-manifest.json
```

### Bước 6 — sửa tham chiếu `hoc/` trong lệnh shell/prose ở 4 bài KHÔNG có link `app/*.py`
`[Red team — Accept, Finding "hoc/00,01,03,09 scratch-file/shell-command refs not covered"]`
4 file `hoc/00-muc-luc.md`, `hoc/01-viet-triage-tu-dau.md`, `hoc/03-safety.md`,
`hoc/09-admin.md` (đã dời tới `docs/hoc/` ở Bước 1) chứa LỆNH SHELL/prose tham chiếu
`hoc/` (không phải link markdown) — các lệnh này resolve theo CWD lúc chạy (thường là gốc
repo), KHÔNG tự động đúng sau khi dời như link markdown. Đọc lại CHÍNH XÁC từng dòng trước
khi sửa (số dòng có thể lệch, đây là vị trí xác nhận qua grep trước khi viết plan):
- `docs/hoc/00-muc-luc.md`: dòng có `hoc/...` trong ví dụ lệnh (bare, không phải link) →
  đổi tiền tố thành `docs/hoc/...`.
- `docs/hoc/01-viet-triage-tu-dau.md`: các lệnh `touch hoc/triage_demo.py`,
  `./.venv/bin/python hoc/triage_demo.py` (và các biến thể tương tự) → đổi
  `hoc/triage_demo.py` thành `docs/hoc/triage_demo.py`.
- `docs/hoc/03-safety.md`: lệnh/prose tham chiếu `hoc/audit_demo.jsonl` hoặc tương tự →
  đổi tiền tố `hoc/` → `docs/hoc/`.
- `docs/hoc/09-admin.md`: tương tự, đổi tiền tố `hoc/` → `docs/hoc/` ở lệnh/prose liên quan.
Grep xác nhận trước khi sửa:
```bash
grep -n "hoc/" docs/hoc/00-muc-luc.md docs/hoc/01-viet-triage-tu-dau.md \
  docs/hoc/03-safety.md docs/hoc/09-admin.md
```
Chỉ sửa dòng tham chiếu tới file THỰC HÀNH (`hoc/xxx.py`, `hoc/xxx.jsonl`) hoặc lệnh `cd`/
`python hoc/...` — KHÔNG sửa các dòng đã là link markdown nội bộ hợp lệ (vd link giữa các
bài `hoc/` với nhau trong `00-muc-luc.md`, đã đúng theo quy tắc ở Bước 3/4).

### Bước 7 — sửa `docs/BAOCAO_DOAN.md` và `docs/BAOCAO_DANHGIA.md`
`[Red team — Accept, Finding "BAOCAO_DOAN.md sơ đồ cây thư mục stale"]`
Đọc lại sơ đồ cây thư mục ASCII trong `docs/BAOCAO_DOAN.md` (mô tả cấu trúc repo tổng thể)
— cập nhật vị trí `eval/results.md`, `eval/rubric.md` (giờ ở `docs/eval/`, không còn ở
`eval/` gốc), `hoc/` (giờ ở `docs/hoc/`), `BAOCAO_DOAN.md`/`BAOCAO_DANHGIA.md` (giờ ở
`docs/`, không còn ở gốc) trong sơ đồ này cho khớp cấu trúc mới.
`[Red team — Accept, Finding "BAOCAO prose mentions of eval/evaluate.py miscategorized"]`
Đọc lại các câu prose (không phải sơ đồ cây) nhắc `eval/evaluate.py` CÙNG câu với
`eval/results.md`/`eval/rubric.md` — sửa riêng phần `eval/evaluate.py` thành
`../eval/evaluate.py` (đi RA NGOÀI `docs/`, vì script này không di chuyển), giữ nguyên
`eval/results.md`/`eval/rubric.md` (đã tình cờ đúng, xem plan.md).

## Related Code Files

- Move (git mv): `hoc/*.md` (10 file) → `docs/hoc/`
- Move (git mv): `eval/rubric.md`, `eval/results.md` → `docs/eval/`
- Move (git mv): `BAOCAO_DOAN.md`, `BAOCAO_DANHGIA.md` → `docs/`
- Modify: `eval/evaluate.py` (`RESULTS_PATH`, docstring prose)
- Modify: `docs/hoc/01-viet-triage-tu-dau.md`, `docs/hoc/02-data.md`,
  `docs/hoc/04-booking.md`, `docs/hoc/05-push.md`, `docs/hoc/06-chatbot.md`,
  `docs/hoc/07-app.md`, `docs/hoc/08-storage-calendar-reminder.md` (link nội bộ)
- Delete (git rm): `release-manifest.json`
- Modify: `docs/hoc/00-muc-luc.md`, `docs/hoc/01-viet-triage-tu-dau.md`,
  `docs/hoc/03-safety.md`, `docs/hoc/09-admin.md` (lệnh shell/prose tham chiếu `hoc/`)
- Modify: `docs/BAOCAO_DOAN.md` (sơ đồ cây thư mục), `docs/BAOCAO_DOAN.md`/
  `docs/BAOCAO_DANHGIA.md` (prose `eval/evaluate.py`)

## Implementation Steps (TDD)

1. **Red (baseline)**: chạy `python3.10 eval/evaluate.py`, xác nhận file `eval/results.md`
   (vị trí CŨ) được ghi/cập nhật — đây là hành vi TRƯỚC khi sửa, dùng làm baseline so sánh.
   Cũng chạy `python3.10 -m pytest tests/ -v` ghi lại baseline (kỳ vọng 92 passed, 1 skipped
   — không phase nào trong plan này đụng `app/`/`tests/`, chỉ verify không bị ảnh hưởng
   ngoài dự kiến).
2. Thực hiện Bước 1 (Architecture) — `git mv` toàn bộ.
3. Thực hiện Bước 2 — sửa `eval/evaluate.py`.
4. Thực hiện Bước 3, 4 — sửa link nội bộ trong 7 file `hoc/*.md` đã dời (đọc lại CHÍNH XÁC
   từng file trước khi sửa, không suy đoán theo pseudocode nếu số dòng lệch).
5. Thực hiện Bước 5 — xoá 2 file thừa.
6. **Green — verify**:
   - `python3.10 eval/evaluate.py` (chạy lại) → xác nhận `docs/eval/results.md` được cập
     nhật (kiểm tra timestamp/nội dung mới), và `eval/results.md` (vị trí CŨ) KHÔNG được
     tạo lại (file không còn tồn tại ở đó, hoặc nếu git chưa dọn sạch, xác nhận không bị
     ghi đè bởi lần chạy mới).
   - `python3.10 -m pytest tests/ -v` → vẫn 92 passed, 1 skipped, không regress.
   `[Red team — Accept, Finding "No post-edit grep verification on evaluate.py"]`
   - Grep hậu-kiểm `eval/evaluate.py`: xác nhận không còn `os.path.dirname(__file__)` gắn
     với `results.md`, và docstring không còn ghi cứng `eval/results.md`:
     ```bash
     grep -n "results.md\|RESULTS_PATH" eval/evaluate.py
     ```
     Xác nhận CHỈ còn đúng 1 định nghĩa `RESULTS_PATH = os.path.join(ROOT, "docs", "eval",
     "results.md")` và không còn chuỗi `eval/results.md` nào khác ngoài dòng docstring đã
     sửa thành `docs/eval/results.md`.
   `[Red team — Accept, Finding "Verification tests hardcoded list not actual edited content"]`
   - Verify link vừa sửa bằng cách TRÍCH XUẤT đường dẫn thật từ file đã sửa (không chỉ dùng
     danh sách "kỳ vọng" viết cứng ở phase file này — để bắt cả lỗi gõ sai path):
     ```bash
     grep -oE '\]\([^)]+\)' docs/hoc/01-viet-triage-tu-dau.md docs/hoc/02-data.md \
       docs/hoc/04-booking.md docs/hoc/05-push.md docs/hoc/06-chatbot.md \
       docs/hoc/07-app.md docs/hoc/08-storage-calendar-reminder.md
     ```
     Với mỗi path trích xuất được (bỏ dấu `](` và `)`), resolve từ vị trí file chứa nó, xác
     nhận `test -f` thành công — không chỉ tin theo danh sách kỳ vọng ở dưới.
   - Kiểm tra từng link vừa sửa TRỎ ĐÚNG FILE THẬT bằng cách resolve đường dẫn thủ công:
     ```bash
     cd docs/hoc && for f in ../../app/triage.py ../../app/data.py ../../app/booking.py \
       ../../app/push.py ../../app/chatbot.py ../../app/app.py ../database-storage-guide.md; do
       test -f "$f" && echo "OK: $f" || echo "MISSING: $f"
     done
     ```
     TẤT CẢ phải in `OK`, không có `MISSING`.
   - `git status` xác nhận toàn bộ move hiển thị `renamed:`/`R`, không phải xoá+tạo tách
     rời.

## Success Criteria

- [x] `docs/hoc/` (10 file), `docs/eval/rubric.md`, `docs/eval/results.md`,
  `docs/BAOCAO_DOAN.md`, `docs/BAOCAO_DANHGIA.md` tồn tại; `hoc/`, `eval/rubric.md`,
  `eval/results.md`, `BAOCAO_DOAN.md`, `BAOCAO_DANHGIA.md` (vị trí cũ) KHÔNG còn.
- [x] `eval/evaluate.py` ghi đúng `docs/eval/results.md` khi chạy thật.
- [x] TẤT CẢ 7 link đã sửa trong `docs/hoc/*.md` resolve đúng file thật (verify bằng lệnh ở
  bước 6, không chỉ đọc bằng mắt).
- [x] `release-manifest.json` đã bị xoá. `.repomixignore` GIỮ NGUYÊN (không đụng).
- [x] 4 file `docs/hoc/00-muc-luc.md`, `docs/hoc/01-viet-triage-tu-dau.md`,
  `docs/hoc/03-safety.md`, `docs/hoc/09-admin.md`: mọi tham chiếu `hoc/` trong lệnh
  shell/prose đã đổi thành `docs/hoc/`.
- [x] `docs/BAOCAO_DOAN.md`: sơ đồ cây thư mục khớp cấu trúc mới; prose `eval/evaluate.py`
  đổi thành `../eval/evaluate.py` ở cả 2 file `BAOCAO_*.md` nếu có.
- [x] `python3.10 -m pytest tests/ -v` vẫn 92 passed, 1 skipped.
- [x] `git status` xác nhận dùng đúng `git mv`/`git rm`.

## Risk Assessment

- **Sai độ sâu tương đối (`../` vs `../../`) là rủi ro chính** — không có công cụ tự động
  kiểm tra link markdown trong repo này, chỉ có thể verify bằng cách RESOLVE THỦ CÔNG (xem
  bước 6) — bắt buộc chạy, không được bỏ qua vì "chắc đúng rồi".
- **`eval/results.md` (vị trí cũ) có thể vẫn còn tồn tại như file "mồ côi" sau `git mv`**
  nếu implement thao tác nhầm (copy thay vì move) — `git status` phải xác nhận KHÔNG có
  entry `eval/results.md` nào ngoài đúng 1 dòng `renamed:` trỏ tới `docs/eval/results.md`.
- **Không dời `eval/` (thư mục) — chỉ dời 2 file `.md` bên trong nó** — `evaluate.py`,
  `dataset.jsonl`, `dataset_complex.jsonl` PHẢI Ở NGUYÊN `eval/`, không đụng (đây không phải
  "tài liệu", là code/data phục vụ eval, ngoài phạm vi "gộp docs").
- **Link markdown vs lệnh shell resolve khác nhau** — link markdown resolve tương đối theo
  file chứa nó (tự động đúng nếu cả nguồn+đích cùng dời), lệnh shell resolve theo CWD lúc
  chạy (KHÔNG tự động đúng). Không áp dụng chung 1 quy tắc "tình cờ đúng" cho cả 2 loại —
  đây là nguyên nhân Bước 6 phải xử lý riêng.
- **`.repomixignore` PHẢI giữ nguyên, không đụng dù trong bất kỳ bước dọn dẹp nào** — đã bị
  loại khỏi phạm vi xoá sau red-team, nhắc lại để tránh implementer xoá nhầm theo thói quen
  "dọn file config thừa".
