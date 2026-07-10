---
phase: 1
title: "Package Skeleton And Core Move"
status: pending
priority: P1
dependencies: []
---

# Phase 1: Tạo package `app/`, dời code + templates + data, sửa import nội bộ

## Overview

Đây là phase NỀN TẢNG — tất cả phase khác phụ thuộc vào phase này xong trước. Tạo package
`app/`, `git mv` 10 file `.py` + `templates/` + 4 data file vào đó, sửa TOÀN BỘ import
CHÉO GIỮA 10 FILE này từ `import X`/`from X import Y` (bare, đúng khi cùng ở gốc) sang
import tương đối (`from . import X`/`from .X import Y`, đúng khi là submodule cùng package).

## Requirements

- Functional: `python3.10 -m app.app` chạy được y hệt `python3.10 app.py` trước đây (cùng
  route, cùng response, cùng log khởi động). `python3.10 -m app.reminder_worker --once/--test/--watch`
  chạy được y hệt cũ.
- Non-functional: KHÔNG đổi bất kỳ logic nghiệp vụ nào bên trong 10 file — CHỈ đổi cách
  import module chéo giữa chúng. Dùng `git mv` (không xoá-tạo-lại) để giữ lịch sử git.

## Architecture

### Bước 1 — Tạo package
```bash
mkdir -p app
touch app/__init__.py   # để RỖNG — không re-export gì (tránh side-effect khi import
                         # app.storage mà vô tình load luôn app.app, tạo Flask instance
                         # + in banner khởi động không mong muốn cho scripts/eval)
```

### Bước 2 — `git mv` 10 file + templates/ + 4 data file
```bash
git mv app.py booking.py calendar_ics.py chatbot.py data.py push.py \
       reminder_worker.py safety.py storage.py triage.py app/
git mv templates app/templates
git mv appointments.json device_tokens.json audit_log.jsonl app/
git mv outbox app/outbox
```
Sau bước này, `os.path.dirname(__file__)` trong `storage.py`/`safety.py`/`push.py` VẪN
TRỎ ĐÚNG (tương đối `app/`, nơi data file cũng vừa dời tới) — KHÔNG cần sửa gì trong logic
path của 3 file này.

**[Red team — Accept, Finding "git mv chỉ dời file đã track"]** `git mv outbox app/outbox`
chỉ di chuyển file ĐÃ ĐƯỢC GIT TRACK (hiện chỉ có `outbox/push_outbox.jsonl`). Nếu môi
trường có file `outbox/*.jsonl` khác CHƯA track (do `.gitignore` có pattern `outbox/`), lệnh
này sẽ bỏ sót, để lại "mồ côi" ở vị trí cũ. Sau khi `git mv`, chạy thêm:
```bash
git status --ignored outbox/ 2>/dev/null
```
Nếu còn output (file untracked sót lại), dời thủ công bằng `mv` thường (không phải
`git mv`, vì chưa track) vào `app/outbox/`.

### Bước 3 — Sửa import nội bộ (bare → relative)

Đọc lại CHÍNH XÁC từng file trước khi sửa (số dòng có thể lệch so với lần scout ban đầu).
Danh sách ĐẦY ĐỦ các chỗ cần đổi (đã xác nhận qua grep trước khi viết plan này, dùng làm
checklist — không suy đoán thêm):

**`app/app.py`** (module-level imports):
```python
import chatbot        # -> from . import chatbot
import booking         # -> from . import booking
import calendar_ics    # -> from . import calendar_ics
import push             # -> from . import push
import storage           # -> from . import storage
```

**`app/reminder_worker.py`**:
```python
import booking   # -> from . import booking
import push        # -> from . import push
```

**`app/booking.py`**:
```python
import storage    # -> from . import storage
from data import DOCTORS, DEPARTMENTS, WORK_SLOTS, generate_available_slots
# -> from .data import DOCTORS, DEPARTMENTS, WORK_SLOTS, generate_available_slots
```

**`app/chatbot.py`** (1 module-level + nhiều lazy-import trong hàm — TẤT CẢ đều phải sửa):
```python
import triage    # -> from . import triage
import booking    # -> from . import booking
import safety      # -> from . import safety
```
Và các lazy import BÊN TRONG hàm (đọc code để xác nhận đúng dòng, đừng bỏ sót cái nào):
- `import push` (2 chỗ khác nhau trong file) → `from . import push`
- `import calendar_ics` (1 chỗ) → `from . import calendar_ics`
- `from data import DEPARTMENTS, SERVICE_INFO` / `from data import DEPARTMENTS` (4 chỗ khác
  nhau, tham số import khác nhau tuỳ chỗ — đọc kỹ từng chỗ, giữ đúng danh sách tên import,
  chỉ đổi `from data import ...` → `from .data import ...`)

**`app/push.py`**:
```python
import storage   # -> from . import storage
```

**`app/safety.py`**:
```python
from triage import _normalize, _strip_accents, _contains_word
# -> from .triage import _normalize, _strip_accents, _contains_word
```
Và lazy import trong hàm: `import storage` (1 chỗ) → `from . import storage`.

**`app/data.py`**:
Lazy import trong hàm: `import storage` (1 chỗ) → `from . import storage`.

**`app/triage.py`**:
```python
from data import DEPARTMENTS   # -> from .data import DEPARTMENTS
```

**`app/calendar_ics.py`**: không có import chéo nào tới 9 file kia (đã xác nhận qua grep
ban đầu) — không cần sửa.

## Related Code Files

- Create: `app/__init__.py` (rỗng)
- Move (git mv): `app.py`, `booking.py`, `calendar_ics.py`, `chatbot.py`, `data.py`,
  `push.py`, `reminder_worker.py`, `safety.py`, `storage.py`, `triage.py` → `app/`
- Move (git mv): `templates/` → `app/templates/`
- Move (git mv): `appointments.json`, `device_tokens.json`, `audit_log.jsonl`, `outbox/`
  → `app/`
- Modify (sau khi move): tất cả 10 file `.py` vừa dời (chỉ phần import, theo Architecture)

## Implementation Steps (TDD cho refactor — Red = baseline, Green = sau khi move)

1. **Red (baseline, TRƯỚC khi đổi bất kỳ thứ gì)**: chạy
   `python3.10 -m pytest tests/ -v` từ gốc repo, ghi lại kết quả CHÍNH XÁC (số pass/skip) —
   đây là baseline phải khớp lại sau Green. Kỳ vọng: 92 passed, 1 skipped (theo trạng thái
   trước phase này).

   **[Red team — Accept, Finding "verify data-integrity chỉ là len>0, không so khớp chính
   xác"]** CÙNG LÚC ghi lại số lượng chính xác:
   ```bash
   python3.10 -c "import storage; print(len(storage.list_appointments()))"
   ```
   Lưu số này làm baseline SỐ LƯỢNG CHÍNH XÁC (không chỉ ">0") — dùng để so khớp ở bước 4
   bên dưới sau khi dời file, thay vì chỉ kiểm tra "còn dữ liệu".
2. Thực hiện Bước 1-2 (Architecture) — tạo package, `git mv` toàn bộ.
3. Thực hiện Bước 3 (Architecture) — sửa import theo checklist, đọc kỹ từng file thay vì
   suy đoán theo pseudocode.
4. **Verify riêng phase này** (tests/ CHƯA được sửa — sẽ fail vì tests còn import kiểu cũ,
   đó là chuyện của Phase 2, KHÔNG phải lỗi của Phase 1):
   - `python3.10 -c "import app.app"` → không lỗi import (xác nhận toàn bộ chuỗi import
     chéo giữa 10 file đã đúng).
   - `python3.10 -c "from app.app import app; print(app.url_map)"` → in ra danh sách route,
     xác nhận Flask app khởi tạo được.
   - `python3.10 -m app.app &` (chạy nền, đợi 1-2s) rồi `curl -s http://127.0.0.1:5001/`
     → phải trả về HTML của `index.html` (KHÔNG phải lỗi 500 "template not found") — xác
     nhận `templates/` đã dời đúng chỗ. Dừng process sau khi test xong
     (`kill %1` hoặc tương đương).
   - `python3.10 -c "import app.storage as storage; print(storage.APPOINTMENTS_PATH); print(len(storage.list_appointments()))"`
     → `APPOINTMENTS_PATH` phải chứa `app/appointments.json` (không phải file rỗng mới).
     **[Red team — Accept]** Số lượng in ra PHẢI BẰNG CHÍNH XÁC baseline đã ghi ở bước 1
     (không chỉ ">0" — so khớp số chính xác để chắc chắn không mất bản ghi nào trong lúc
     dời).
5. Chạy `git status` xác nhận toàn bộ move dùng đúng `git mv` (hiển thị `renamed:`, không
   phải `deleted:` + `new file:` riêng lẻ — nếu thấy tách rời, có nghĩa đã dùng `mv` +
   `git add` thay vì `git mv`, cần làm lại đúng cách để giữ lịch sử).

## Success Criteria

- [ ] `app/__init__.py` tồn tại, rỗng.
- [ ] 10 file `.py` + `templates/` + 4 data file đã ở trong `app/`, dùng `git mv` (giữ
  lịch sử).
- [ ] `python3.10 -c "import app.app"` không lỗi.
- [ ] `python3.10 -m app.app` chạy được, `curl /` trả về HTML đúng (template resolve đúng).
- [ ] `app.storage.APPOINTMENTS_PATH` trỏ đúng `app/appointments.json` có dữ liệu cũ, không
  phải file rỗng mới.
- [ ] KHÔNG có import bare `import chatbot`/`import booking`/v.v. VÀ KHÔNG có
  `from data import ...`/`from triage import ...` bare còn sót lại trong 10 file.
  **[Red team — Accept, Finding "grep cũ chỉ khớp ^import, mù trước from X import Y — đúng
  loại rủi ro Risk Assessment tự gọi là lớn nhất"]** Grep xác nhận PHẢI khớp CẢ 2 dạng, và
  KHÔNG neo `^` (để bắt được lazy-import thụt lề trong hàm — đây chính xác là nơi rủi ro
  lớn nhất theo Risk Assessment bên dưới):
  ```bash
  grep -rn "import \(booking\|chatbot\|safety\|storage\|triage\|push\|calendar_ics\|data\|app\|reminder_worker\)\b" app/*.py \
    | grep -v "^app/[a-z_]*\.py:[0-9]*: *from \.\|^app/[a-z_]*\.py:[0-9]*: *from \. import"
  ```
  Kết quả PHẢI RỖNG (loại trừ đúng các dòng `from .` hợp lệ). Nếu câu lệnh trên khó viết
  đúng regex loại trừ, làm đơn giản hơn: `grep -rn "^\s*\(import\|from\) \(booking\|chatbot\|safety\|storage\|triage\|push\|calendar_ics\|data\|app\|reminder_worker\)\b" app/*.py`
  rồi ĐỌC BẰNG MẮT từng dòng trả về, xác nhận TẤT CẢ đều bắt đầu bằng `from .` (relative) —
  không có dòng nào là `import X`/`from X import Y` bare.

## Risk Assessment

- **Bỏ sót 1 lazy-import trong `chatbot.py`** (file này có NHIỀU chỗ import rải rác trong
  hàm, không tập trung ở đầu file) là rủi ro lớn nhất — 1 chỗ sót sẽ gây `ImportError`/
  `ModuleNotFoundError` CHỈ KHI code chạy tới đúng nhánh đó (không lộ ra ngay khi chạy
  `import app.app`), có thể sống sót qua bước verify 4 mà vẫn lỗi khi test suite (Phase 2)
  chạy tới nhánh cụ thể đó. Bước 3 liệt kê ĐẦY ĐỦ checklist các lazy-import đã grep được —
  bám sát checklist, không tự tin bỏ qua bước đọc lại code.
- **`app/__init__.py` để rỗng có chủ đích** — nếu re-export Flask `app` instance ở đó (vd
  `from app.app import app`), MỌI lần `import app.X` (kể cả từ scripts chỉ cần `storage`)
  sẽ kích hoạt tạo Flask instance + in banner khởi động + khởi tạo rate-limiter state như
  tác dụng phụ không mong muốn. Giữ rỗng để `app.X` chỉ load đúng module cần, không kéo
  theo side-effect.
- **`python3.10 -m app.app` khác `python3.10 app/app.py`** — chạy trực tiếp file
  (`python app/app.py`) SẼ LỖI vì import tương đối (`from . import X`) không hoạt động khi
  file được chạy như script độc lập (không phải qua `-m`). Đây là hành vi CHỦ Ý, không phải
  bug — luôn dùng `-m app.app`, không dùng `python app/app.py`. Ghi rõ trong Phase 4 (docs).
