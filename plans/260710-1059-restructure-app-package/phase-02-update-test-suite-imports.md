---
phase: 2
title: "Update Test Suite Imports"
status: pending
priority: P1
dependencies: [1]
---

# Phase 2: Sửa import trong toàn bộ `tests/`

## Overview

14 file test + `tests/conftest.py` hiện `import` các module bằng tên bare (`import booking`,
`from data import ...`, `import app as app_module`, v.v.) — đúng khi các module này nằm ở
gốc repo (cùng thư mục với chỗ pytest chạy). Sau Phase 1, các module này là submodule của
package `app/` — mọi import trong `tests/` phải đổi sang dạng ABSOLUTE qua package
(`from app import booking`, `from app.data import ...`) — KHÔNG dùng relative import (`tests/`
không phải submodule của `app/`, chỉ có code BÊN TRONG `app/` mới dùng relative).

**PHỤ THUỘC Phase 1**: package `app/` phải tồn tại và import được trước khi phase này bắt
đầu, nếu không mọi test sẽ collection-error ngay từ đầu.

## Requirements

- Functional: `python3.10 -m pytest tests/ -v` pass 100% giống hệt baseline Phase 1 (92
  passed, 1 skipped) — KHÔNG có test nào bị sửa nội dung assert/logic, CHỈ sửa dòng import.
- Non-functional: monkeypatch/mock trong test (vd `monkeypatch.setattr(storage, "USE_DB",
  False)`) vẫn hoạt động đúng SAU khi đổi cách import module — vì Python module object là
  singleton theo đường dẫn import đầy đủ (`app.storage`), monkeypatch trên object đó vẫn
  ảnh hưởng đúng instance mà code thật (`app/booking.py`'s `from . import storage`) đang
  dùng — không có rủi ro "2 bản module khác nhau" MIỄN LÀ import luôn nhất quán qua
  `app.X`, không trộn lẫn kiểu import cũ/mới.

## Architecture

Nguyên tắc đổi (áp dụng cho MỌI file `tests/*.py`):
```python
# CŨ (bare, đúng khi module ở gốc repo)
import booking
import storage
import chatbot
import safety
from data import DOCTORS, DEPARTMENTS, generate_available_slots
from triage import _normalize, _strip_accents
import app as app_module

# MỚI (absolute qua package app/)
from app import booking
from app import storage
from app import chatbot
from app import safety
from app.data import DOCTORS, DEPARTMENTS, generate_available_slots
from app.triage import _normalize, _strip_accents
from app import app as app_module
```
`tests/conftest.py` là chỗ QUAN TRỌNG NHẤT phải đúng — nó hiện có `import app as app_module`
rồi dùng `app_module._RATE_BUCKETS` (biến sống trong module Flask, không phải trong
`app/__init__.py` rỗng). Nếu chỉ đổi thành `import app` (không đổi gì thêm), `app_module`
sẽ trỏ vào PACKAGE `app/__init__.py` (rỗng, không có `_RATE_BUCKETS`) → `AttributeError`
ngay khi fixture chạy, làm HỎNG TOÀN BỘ SUITE (fixture này là `autouse=True`, chạy trước
MỌI test). Phải đổi CHÍNH XÁC thành `from app import app as app_module` (import submodule
`app.app`, đặt tên cục bộ là `app_module` để không đổi phần code còn lại của file).

**[Red team — Accept, Finding "Phase 2 chỉ mẫu hoá kiểu import CÓ ALIAS, bỏ sót kiểu KHÔNG
ALIAS đang dùng ở 2 file khác"]** KHÔNG PHẢI mọi file test dùng CÙNG 1 kiểu import Flask
module. Có 2 nhóm khác nhau, phải xử lý ĐÚNG TỪNG NHÓM (đọc từng file để biết nó thuộc
nhóm nào, không áp 1 mẫu chung cho tất cả):

- **Nhóm A — đã alias `app_module`** (`tests/conftest.py`, `tests/test_app_ics.py`): giữ
  nguyên tên cục bộ `app_module`, chỉ đổi vế phải: `import app as app_module` →
  `from app import app as app_module`.
- **Nhóm B — KHÔNG alias, dùng thẳng tên `app`** (`tests/test_app_admin.py`,
  `tests/test_app_hardening.py` — 2 file này hiện `import app` TRƠN rồi dùng thẳng
  `app.ADMIN_KEY`, `app.app.config[...]`, `app._default_key_warnings(...)` trong thân bài
  test): đổi thành `from app import app` (KHÔNG thêm alias `as app_module` — nếu thêm alias
  vào 2 file này sẽ làm MỌI tham chiếu `app.` còn lại trong file đó thành `NameError` vì tên
  cục bộ `app` không còn tồn tại). Giữ nguyên tên `app` để toàn bộ thân bài test không cần
  sửa gì thêm ngoài dòng import.

Trước khi sửa BẤT KỲ file nào trong 4 file trên, chạy `grep -n "^import app\|app_module\|app\.app\.\|app\.ADMIN_KEY\|app\._" tests/test_app_admin.py tests/test_app_hardening.py tests/test_app_ics.py tests/conftest.py` để tự xác nhận file đó thuộc nhóm A hay B — không suy đoán theo danh sách trên (danh sách chỉ là kết quả scout tại thời điểm viết plan).

## Related Code Files

- Modify: `tests/conftest.py` (ưu tiên sửa ĐẦU TIÊN, vì `autouse=True` — sai chỗ này làm
  hỏng mọi test khác)
- Modify: `tests/test_app_admin.py`, `tests/test_app_hardening.py`, `tests/test_app_ics.py`,
  `tests/test_booking.py`, `tests/test_calendar_ics.py`, `tests/test_chatbot_audit.py`,
  `tests/test_chatbot_guardrail.py`, `tests/test_chatbot_session_lock.py`,
  `tests/test_chatbot_sessions.py`, `tests/test_push.py`, `tests/test_reminder_worker.py`,
  `tests/test_safety.py`, `tests/test_storage.py` (13 file — đọc TỪNG FILE để tìm chính xác
  dòng import cần đổi, KHÔNG suy đoán có bao nhiêu chỗ mỗi file, dùng grep xác nhận trước)

## Implementation Steps (TDD cho refactor)

1. **Xác nhận Phase 1 đã xong**: chạy `python3.10 -c "import app.app"` → phải KHÔNG lỗi
   trước khi bắt đầu phase này.
2. **Grep TOÀN BỘ import cần đổi trước khi sửa** (không đoán số lượng):
   ```bash
   grep -rn "^import \(booking\|chatbot\|safety\|storage\|triage\|push\|calendar_ics\|data\|app\|reminder_worker\)\b\|^from \(booking\|chatbot\|safety\|storage\|triage\|push\|calendar_ics\|data\|app\|reminder_worker\) import" tests/
   ```
   Dùng kết quả này làm checklist đầy đủ — sửa HẾT, không dựa vào trí nhớ từ lần scout
   trước khi viết plan (số dòng/số chỗ có thể lệch).
3. Sửa `tests/conftest.py` TRƯỚC (theo Architecture, chú ý đúng
   `from app import app as app_module`). Sau đó xử lý `tests/test_app_ics.py` (Nhóm A, cùng
   kiểu alias) rồi `tests/test_app_admin.py`/`tests/test_app_hardening.py` (Nhóm B, KHÔNG
   alias — xem Architecture để tránh `NameError`).
4. Chạy `python3.10 -m pytest tests/conftest.py --collect-only` (hoặc chạy 1 test bất kỳ,
   vd `python3.10 -m pytest tests/test_safety.py -v`) để xác nhận fixture `autouse` không
   crash trước khi sửa tiếp 13 file còn lại.
5. Sửa từng file test còn lại theo checklist bước 2.
6. **Green**: chạy `python3.10 -m pytest tests/ -v` toàn bộ → PHẢI khớp CHÍNH XÁC baseline
   Phase 1 (92 passed, 1 skipped, cùng tên test, không có test nào mới fail/bị skip thêm).

## Success Criteria

- [ ] `python3.10 -m pytest tests/ -v` → 92 passed, 1 skipped (khớp baseline).
- [ ] `tests/conftest.py` dùng `from app import app as app_module`, KHÔNG phải `import app`
  trơn.
- [ ] Không còn import bare nào tới 10 module trong `tests/*.py` (grep xác nhận lại theo
  câu lệnh ở bước 2, kết quả phải rỗng).
- [ ] KHÔNG có test nào bị sửa nội dung logic/assert — chỉ dòng import thay đổi (diff review
  bằng mắt xác nhận).

## Risk Assessment

- **`tests/conftest.py` sai là rủi ro lớn nhất** — 1 dòng sai làm TOÀN BỘ 93 test fail cùng
  lúc do fixture `autouse`. Bước 3-4 tách riêng để phát hiện sớm trước khi lan ra 13 file
  còn lại.
- **Monkeypatch nhắm sai module object** nếu code thật (`app/`) và test dùng 2 cách import
  KHÔNG nhất quán (vd code thật dùng `from . import storage` nhưng lỡ còn 1 chỗ test cũ
  import kiểu module top-level `storage` thay vì `app.storage` do sót ở bước 2) — Python sẽ
  coi đây là 2 module KHÁC NHAU trong `sys.modules` (`storage` vs `app.storage`), monkeypatch
  trên 1 bên không ảnh hưởng bên kia, test PASS giả (không phát hiện được bug thật). Đây là
  lý do bước 2 phải grep TRIỆT ĐỂ, không được sót 1 chỗ nào.
