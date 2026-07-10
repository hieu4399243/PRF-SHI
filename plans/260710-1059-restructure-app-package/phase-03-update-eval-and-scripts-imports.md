---
phase: 3
title: "Update Eval And Scripts Imports"
status: pending
priority: P2
dependencies: [1]
---

# Phase 3: Sửa import trong `eval/evaluate.py` và `scripts/*.py`

## Overview

`eval/evaluate.py`, `scripts/clean_stale_appointments.py`, `scripts/migrate_to_supabase.py`
đều đã có sẵn `sys.path.insert(0, ROOT)` để import module từ gốc repo (`ROOT` =
`os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`, TRỎ ĐÚNG gốc repo, KHÔNG
cần sửa dòng này). Sau Phase 1, các module cần import qua package `app.` thay vì bare.

**PHỤ THUỘC Phase 1**: package `app/` phải tồn tại trước.

## Requirements

- Functional: `python3.10 eval/evaluate.py` chạy được y hệt trước (đọc `eval/dataset.jsonl`,
  in kết quả, ghi `eval/results.md`). `python3.10 scripts/clean_stale_appointments.py`
  (dry-run) và `python3.10 scripts/migrate_to_supabase.py` chạy được y hệt trước (không cần
  test full DB flow nếu không có `DATABASE_URL` local — chỉ cần import thành công + không
  crash ở phần logic không phụ thuộc DB thật).
- Non-functional: KHÔNG đổi `sys.path.insert(...)` (đã đúng, trỏ gốc repo — sau khi `app/`
  là 1 thư mục con của gốc, `ROOT` trên `sys.path` làm `import app` (package) hoạt động
  đúng). CHỈ đổi các dòng `import triage`/`from data import ...`/`import storage` bên dưới.

## Architecture

**`eval/evaluate.py`**:
```python
import triage                    # -> KHÔNG XOÁ dòng sys.path.insert phía trên
from data import DEPARTMENTS
```
đổi thành:
```python
from app import triage
from app.data import DEPARTMENTS
```

**`scripts/clean_stale_appointments.py`**:
```python
import storage
from data import DOCTORS
```
đổi thành:
```python
from app import storage
from app.data import DOCTORS
```

**`scripts/migrate_to_supabase.py`**: đọc file để xác nhận import chính xác (chỉ thấy
`import storage` qua grep ban đầu, có thể có thêm import khác chưa grep hết — đọc lại toàn
bộ phần đầu file trước khi sửa) — áp dụng cùng nguyên tắc: `import storage` →
`from app import storage`.

**[Red team — Accept, Finding "migrate_to_supabase.py tự tính path riêng, KHÔNG qua
storage.py — CRITICAL, CẢ 3 REVIEWER ĐỘC LẬP CÙNG BẮT"]** File này KHÔNG CHỈ có `import
storage` cần đổi — nó còn tự định nghĩa 2 HẰNG SỐ ĐƯỜNG DẪN RIÊNG, độc lập với
`storage.py`, đọc thẳng `appointments.json`/`device_tokens.json` ở gốc repo (biến `ROOT`):
```python
APPTS = os.path.join(ROOT, "appointments.json")     # SAI sau khi Phase 1 dời file
TOKENS = os.path.join(ROOT, "device_tokens.json")   # SAI sau khi Phase 1 dời file
```
Code đọc 2 file này có `if os.path.exists(APPTS) else []` / tương tự cho `TOKENS` — sau khi
Phase 1 dời `appointments.json`/`device_tokens.json` vào `app/`, `os.path.exists(APPTS)`
trả `False`, script ÂM THẦM coi như "0 bản ghi", in ra kiểu
`✅ Đã nạp 0 lịch hẹn (bỏ qua 0 đã có).` — TRÔNG NHƯ THÀNH CÔNG nhưng thực ra đã bỏ sót TOÀN
BỘ dữ liệu thật khi migrate lên Supabase. Đây là dạng lỗi nguy hiểm nhất (không crash, không
log lỗi, chỉ âm thầm sai).

**Fix bắt buộc**: XOÁ 2 dòng tự định nghĩa `APPTS`/`TOKENS` bằng `ROOT`, THAY BẰNG tái sử
dụng path CHÍNH CHỦ đã có sẵn trong `storage.py` (đây là cách đúng về kiến trúc — không nên
có 2 nơi biết vị trí file dữ liệu, `storage.py` đã là nguồn chân lý duy nhất từ trước, xem
`docs/database-storage-guide.md`):
```python
from app import storage
...
APPTS = storage.APPOINTMENTS_PATH
TOKENS = storage.TOKENS_PATH
```
Đọc lại TOÀN BỘ file `scripts/migrate_to_supabase.py` để xác nhận đúng tên biến `APPTS`/
`TOKENS` hiện tại (có thể lệch tên so với plan này viết, tuỳ code thật) và đúng chỗ dùng
`ROOT` cho 2 hằng số này — chỉ xoá phần tính `ROOT`-relative cho ĐÚNG 2 file dữ liệu này,
KHÔNG đụng `ROOT` dùng cho `sys.path.insert` (vẫn cần giữ, xem Requirements).

## Related Code Files

- Modify: `eval/evaluate.py`
- Modify: `scripts/clean_stale_appointments.py`
- Modify: `scripts/migrate_to_supabase.py`

## Implementation Steps (TDD cho refactor)

1. **Xác nhận Phase 1 đã xong**: `python3.10 -c "import app.app"` không lỗi.
2. **Đọc lại từng file** (`eval/evaluate.py`, cả 2 file trong `scripts/`) để xác nhận
   TOÀN BỘ import cần đổi — không dựa hoàn toàn vào Architecture ở trên nếu đọc thấy có
   thêm chỗ chưa liệt kê.
3. Sửa import theo Architecture, GIỮ NGUYÊN `sys.path.insert(...)` không đụng.
4. **Verify**:
   - `python3.10 eval/evaluate.py` → chạy xong, in kết quả Accuracy/F1, ghi
     `eval/results.md` (so sánh nội dung trước/sau nếu cần, phải giống hệt vì logic
     `triage`/`data` không đổi).
   - `python3.10 scripts/clean_stale_appointments.py` (KHÔNG kèm `--apply`, chế độ dry-run
     mặc định, an toàn) → chạy xong không lỗi import. Nếu môi trường không có `DATABASE_URL`
     và script yêu cầu DB, ghi rõ trong báo cáo hoàn thành là chỉ verify được phần import,
     không verify được luồng DB thật.
   - `python3.10 -c "import ast; ast.parse(open('scripts/migrate_to_supabase.py').read())"`
     (syntax check tối thiểu nếu không thể chạy full script do cần `DATABASE_URL`) — hoặc
     chạy thật nếu môi trường cho phép.

## Success Criteria

- [ ] `eval/evaluate.py` chạy được, kết quả giống hệt trước restructure.
- [ ] `scripts/clean_stale_appointments.py` import thành công, dry-run chạy được.
- [ ] `scripts/migrate_to_supabase.py` import thành công (verify tối thiểu qua syntax/import
  check nếu không có DB thật để test full).
- [ ] `scripts/migrate_to_supabase.py` KHÔNG còn tự định nghĩa `APPTS`/`TOKENS` bằng
  `ROOT`-relative path — dùng `storage.APPOINTMENTS_PATH`/`storage.TOKENS_PATH`. Verify đơn
  giản: `grep -n "APPTS\|TOKENS" scripts/migrate_to_supabase.py` → xác nhận bằng mắt cả 2
  biến được gán từ `storage.APPOINTMENTS_PATH`/`storage.TOKENS_PATH`, không còn
  `os.path.join(ROOT, "appointments.json")`/`os.path.join(ROOT, "device_tokens.json")`.
- [ ] `sys.path.insert(...)` trong cả 3 file GIỮ NGUYÊN không đổi.

## Risk Assessment

- **`ROOT` trong `sys.path.insert` đã đúng sẵn** (trỏ gốc repo, KHÔNG phải `app/`) — không
  có rủi ro path sai ở đây, chỉ cần đổi phần import bên dưới. Nếu implement thấy cần sửa
  `ROOT`, đó là dấu hiệu đọc sai — `ROOT` không nên đổi.
- **`scripts/migrate_to_supabase.py` có thể cần `DATABASE_URL` thật để test full** — chấp
  nhận verify giới hạn (import + syntax) nếu môi trường dev không có Postgres, ghi rõ giới
  hạn này trong báo cáo hoàn thành, không tự nhận "đã test đầy đủ" nếu chưa chạy thật.
