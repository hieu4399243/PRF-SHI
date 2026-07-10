---
phase: 1
title: "Move Data Files And Update Path Constants"
status: completed
priority: P1
dependencies: []
---

# Phase 1: Dời data file vào `app/data/`, sửa path constant, verify không mất dữ liệu

## Overview

Phase NỀN TẢNG — gộp 3 file JSON/JSONL rải rác + `outbox/` vào `app/data/`, sửa đồng thời
3 module (`storage.py`, `safety.py`, `push.py`) trong CÙNG 1 bước để tránh trạng thái
half-migrated (nếu chỉ dời file mà chưa sửa path, app sẽ tạo file rỗng mới ở vị trí cũ).

## Requirements

- Functional: `app/data/appointments.json`, `app/data/device_tokens.json`,
  `app/data/audit_log.jsonl`, `app/data/outbox/push_outbox.jsonl` tồn tại với ĐÚNG nội dung
  đã có (không mất dữ liệu). App khởi động và hoạt động bình thường với path mới.
- Non-functional: dùng `git mv`. Không đổi hành vi nghiệp vụ, chỉ đổi vị trí file + path
  constant.

## Architecture

### Bước 0 — Pre-flight: kill process cũ còn sống
`[Red team — Accept, Finding "stale running Flask process can silently recreate empty data files mid-migration"]`
```bash
ps aux | grep -i "app\.app\|reminder_worker" | grep -v grep
```
Nếu có process nào đang chạy (từ session trước, `python -m app.app` hoặc
`python -m app.reminder_worker`), KILL trước khi tiếp tục — `app.py` chạy `debug=True`
(Werkzeug reloader chỉ theo dõi file `.py`, KHÔNG theo dõi data file). Process cũ giữ path
constant cũ có thể ghi audit log/lưu appointment vào path SAI ngay giữa lúc dời file.

### Bước 1 — Baseline (Red)
```bash
python3.10 -m pytest tests/ -v 2>&1 | tail -5
python3.10 -c "import json; print('appointments:', len(json.load(open('app/appointments.json'))))"
python3.10 -c "import json; print('tokens:', len(json.load(open('app/device_tokens.json'))))"
git ls-files app/outbox/ app/appointments.json app/device_tokens.json app/audit_log.jsonl
```
Ghi lại: số test pass/skip, số lịch hẹn, số token, và file nào ĐANG được git track (để biết
sau khi dời có cần `git mv` hay `mv` thường cho từng file).

### Bước 2 — Tạo thư mục + `git mv`
```bash
mkdir -p app/data
git mv app/appointments.json app/data/appointments.json
git mv app/device_tokens.json app/data/device_tokens.json
git mv app/audit_log.jsonl app/data/audit_log.jsonl
git mv app/outbox app/data/outbox
```
Nếu bất kỳ file nào ở Bước 1 KHÔNG được git track (`git ls-files` không trả về), dùng `mv`
thường + `git add` cho riêng file đó thay vì `git mv` (không có lịch sử để giữ).
`[Red team — Accept, Finding ".gitignore outbox/ framing incomplete — git mv is mandatory not just history-preserving"]`
**LƯU Ý:** `push_outbox.jsonl` đang khớp pattern `.gitignore`'s `outbox/` NHƯNG vẫn được
track (file track từ trước không tự bị bỏ track). PHẢI dùng `git mv` cho file này (không
phải `mv` thường), nếu không file sẽ "biến mất" khỏi git tracking sau khi dời vì path mới
khớp ignore pattern trong khi git không tự động `git add -f` cho file mới.

**Gate khi resume sau gián đoạn:** nếu Bước 2 tới Bước 5 bị ngắt giữa chừng (mất context,
lỗi tool, session mới), TRƯỚC KHI làm bất kỳ việc gì khác (kể cả chạy thử app), chạy
`git status --short app/` — nếu thấy `git mv` đã xong nhưng path constant CHƯA sửa hết (hoặc
ngược lại), sửa nốt phần còn thiếu NGAY LẬP TỨC. Đây là trạng thái half-migrated nguy hiểm
nhất của cả plan.

### Bước 3 — Sửa `app/storage.py` (đọc lại số dòng thật trước khi sửa)
```python
_BASE = os.path.dirname(__file__)
```
→
```python
_BASE = os.path.join(os.path.dirname(__file__), "data")
```
`APPOINTMENTS_PATH`, `TOKENS_PATH` dùng lại `_BASE` — không sửa riêng.

### Bước 4 — Sửa `app/safety.py`
```python
AUDIT_LOG_PATH = os.path.join(os.path.dirname(__file__), "audit_log.jsonl")
```
→
```python
AUDIT_LOG_PATH = os.path.join(os.path.dirname(__file__), "data", "audit_log.jsonl")
```

### Bước 5 — Sửa `app/push.py`
```python
OUTBOX_DIR = os.path.join(os.path.dirname(__file__), "outbox")
```
→
```python
OUTBOX_DIR = os.path.join(os.path.dirname(__file__), "data", "outbox")
```
`OUTBOX_PATH` dùng lại `OUTBOX_DIR` — không sửa riêng.

### Bước 6 — Verify không có nơi nào khác tự tính path riêng
`[Red team — Accept, Finding "grep sweep scoped too narrowly"]`
```bash
grep -rn "appointments.json\|device_tokens.json\|audit_log.jsonl\|outbox" \
  app/*.py scripts/*.py tests/conftest.py eval/*.py
```
(Mở rộng thêm `eval/*.py` so với draft ban đầu — bỏ sót ở lần scout đầu. Không có trang
admin `.py` riêng ngoài `app/app.py` đã nằm trong `app/*.py`, không cần thêm path khác.)
Xác nhận: `scripts/migrate_to_supabase.py` dùng `storage.APPOINTMENTS_PATH`/
`storage.TOKENS_PATH` (không tự tính path) — nếu phát hiện chỗ tự tính path riêng KHÔNG
dùng constant từ `storage.py`/`safety.py`/`push.py`, phải sửa để dùng lại constant (đúng
bug pattern đã gặp ở plan `restructure-app-package` trước).

## Related Code Files

- Move (git mv): `app/appointments.json`, `app/device_tokens.json`, `app/audit_log.jsonl`
  → `app/data/`; `app/outbox/` → `app/data/outbox/`
- Modify: `app/storage.py` (`_BASE`), `app/safety.py` (`AUDIT_LOG_PATH`), `app/push.py`
  (`OUTBOX_DIR`)

## Implementation Steps (TDD)

1. Bước 1 (Architecture) — Red baseline: pytest + đếm chính xác appointments/tokens + ghi
   lại danh sách file đang track.
2. Bước 2 — `git mv` toàn bộ (hoặc `mv`+`git add` cho file chưa track).
3. Bước 3, 4, 5 — sửa 3 path constant, đọc lại số dòng thật trước khi sửa (không suy đoán
   theo pseudocode nếu số dòng lệch).
4. Bước 6 — grep xác nhận không có chỗ tự tính path riêng.
5. **Green — verify:**
   - `python3.10 -m pytest tests/ -v` → khớp 100% baseline Bước 1.
   - Đếm lại appointments/tokens trong `app/data/*.json` → khớp CHÍNH XÁC số ở Bước 1.
   - `python3.10 -m app.app &` (chạy nền), `curl -s http://127.0.0.1:5001/api/start` → xác
     nhận HTTP 200 / response hợp lệ, sau đó kill process.
   - Xác nhận `app/appointments.json`, `app/device_tokens.json`, `app/audit_log.jsonl`,
     `app/outbox/` (vị trí CŨ) KHÔNG bị tạo lại sau khi chạy app (`test -e` phải fail).
   - `[Red team — Accept, Finding "pycache not cleared before verify"]` Xoá
     `app/__pycache__/` trước khi verify import (bytecode cache cũ có thể che giấu lỗi
     import thật): `rm -rf app/__pycache__`.
   - `python3.10 -c "from app import data; print(data.__file__)"` → PHẢI in ra đường dẫn
     `.../app/data.py`, KHÔNG phải thư mục `app/data/` hay lỗi import. Đây là verify bắt
     buộc cho rủi ro đặt tên đã nêu ở plan.md — nếu FAIL, dừng lại và báo cáo, KHÔNG tự ý
     đổi tên thư mục (đây là quyết định đặt tên đã chốt với user, không tự ý đảo ngược).
   - `git status` xác nhận `.gitignore`'s bare `outbox/` pattern vẫn ignore đúng
     `app/data/outbox/` như hành vi cũ (so khớp với danh sách track ở Bước 1 — nếu trước đó
     `push_outbox.jsonl` bị ignore/không track, sau khi dời cũng phải vậy; nếu trước đó CÓ
     track, sau khi dời cũng phải còn track — xem lưu ý `git mv` bắt buộc ở Bước 2).
   - `[Red team — Accept, Finding "pytest dirties audit_log/outbox files, no cleanup before final git status"]`
     Chạy pytest + verify HTTP ở trên có thể ghi entry thật vào
     `app/data/audit_log.jsonl`/`app/data/outbox/push_outbox.jsonl` — TRƯỚC KHI `git status`
     xác nhận CUỐI CÙNG, chạy `git checkout -- app/data/audit_log.jsonl
     app/data/outbox/push_outbox.jsonl` (nếu 2 file có nội dung tracked từ trước) để tránh
     lẫn nhiễu do chạy test/verify với diff thao tác dời file thật.

## Success Criteria

- [x] `app/data/appointments.json`, `app/data/device_tokens.json`,
  `app/data/audit_log.jsonl`, `app/data/outbox/push_outbox.jsonl` tồn tại; vị trí cũ KHÔNG
  còn.
- [x] `storage.py`, `safety.py`, `push.py` sửa đúng 3 path constant, verify bằng chạy thật.
- [x] Số lịch hẹn/token khớp CHÍNH XÁC baseline (không mất dữ liệu, không tạo file rỗng
  mới).
- [x] `from app import data` verify chạy thật resolve đúng `app/data.py`.
- [x] Không có chỗ nào tự tính path riêng ngoài 3 constant đã sửa (grep xác nhận).
- [x] `python3.10 -m pytest tests/ -v` khớp 100% baseline.
- [x] `python3.10 -m app.app` chạy được, `/api/start` trả HTTP 200 (verify curl thật).
- [x] `git status` xác nhận dùng đúng `git mv` (kể cả `push_outbox.jsonl` dù khớp
  `.gitignore` pattern).
- [x] Không có process Flask/worker cũ nào còn sống trước khi bắt đầu dời file.
- [x] `app/__pycache__/` đã xoá trước khi verify import `from app import data`.

## Risk Assessment

- **Rủi ro lớn nhất: sửa path constant SAU KHI dời file (hoặc ngược lại) tạo trạng thái
  half-migrated** — nếu app chạy giữa chừng lúc file đã dời nhưng path constant chưa sửa
  (hoặc ngược lại), sẽ tạo file rỗng mới ở vị trí sai, mất dữ liệu âm thầm. Thực hiện dời +
  sửa constant trong CÙNG 1 lần chạy liên tục, không tách rời, không chạy app ở giữa.
- **`app/data.py` vs `app/data/` trùng tên** — xem plan.md phần "rủi ro đặt tên". PHẢI verify
  bằng lệnh import thật, không chỉ tin lý thuyết Python import resolution.
- **`.gitignore` bare `outbox/` có thể khớp sai cấp** — verify bằng `git status` so khớp
  hành vi track/ignore TRƯỚC và SAU khi dời, không giả định.
- **File chưa track (nếu `push_outbox.jsonl` bị `.gitignore` từ đầu, `git mv` sẽ lỗi)** —
  đã có bước fallback ở Bước 2 (`mv` + `git add` nếu không track).
