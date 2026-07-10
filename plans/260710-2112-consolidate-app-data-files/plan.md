---
title: "Consolidate app/ JSON data files into app/data/ folder"
description: "Dời appointments.json, device_tokens.json, audit_log.jsonl (đang rải ở gốc app/) và outbox/push_outbox.jsonl vào 1 thư mục app/data/ duy nhất. Sửa path constant trong storage.py/safety.py/push.py, .gitignore, và mọi cross-reference trong docs/README."
status: completed
priority: P2
branch: "main"
tags: ["refactor", "tdd"]
blockedBy: []
blocks: []
created: "2026-07-10T14:14:26.511Z"
createdBy: "ck:plan"
source: skill
---

# Consolidate app/ JSON data files into app/data/ folder

## Overview

3 file dữ liệu runtime (`appointments.json`, `device_tokens.json`, `audit_log.jsonl`) đang
nằm rải ở gốc `app/` lẫn với code `.py` — không gọn. Đã có sẵn `app/outbox/` (1 thư mục
con chứa `push_outbox.jsonl`). Plan này gộp cả 4 file vào 1 thư mục `app/data/` duy nhất.

**Quyết định đã chốt với user:**
1. Tên thư mục mới: **`app/data/`**.
2. `app/outbox/` gộp luôn vào — thành `app/data/outbox/push_outbox.jsonl` (giữ nguyên cấu
   trúc con `outbox/` bên trong `data/`, không flatten `push_outbox.jsonl` ra ngang hàng với
   3 file kia — `push.py` đã dùng biến `OUTBOX_DIR` riêng để `os.makedirs`, giữ cấu trúc này
   giảm rủi ro).

## 1 rủi ro kỹ thuật ẩn đã phát hiện qua scout (PHẢI xử lý, không phải optional)

**Cùng loại lỗi đã gặp 2 lần trước (`app/` restructure, `docs/` consolidation):**
`storage.py`, `safety.py`, `push.py` định vị data file qua `os.path.dirname(__file__)`.
Dời data file mà KHÔNG sửa 3 path constant này sẽ khiến app ÂM THẦM tạo file rỗng mới ở vị
trí cũ, MẤT DỮ LIỆU hiện có (11 lịch hẹn theo baseline các plan trước), không báo lỗi gì.
**Fix: sửa cả 3 module cùng lúc trong 1 phase (không tách phase riêng để tránh trạng thái
half-migrated).**

## 1 rủi ro đặt tên cần verify bằng thực nghiệm (không chỉ suy luận)

`app/data.py` (module code, danh mục dịch vụ/nha sĩ/khung giờ) đã tồn tại. Tạo thêm thư mục
`app/data/` (không có `__init__.py`, chỉ chứa data file) tạo ra 1 file `.py` và 1 thư mục
CÙNG TÊN `data` trong cùng `app/`. Về lý thuyết, CPython's import resolution ưu tiên module
file thường (`data.py`) trước namespace-package-portion (thư mục không `__init__.py`) khi
cả hai cùng khớp tên trong cùng 1 path entry — nên các import thật đang dùng trong code (vd
`from .data import SERVICES` ở `chatbot.py:309,335,350,448`, `booking.py:16`,
`triage.py:20` — **không phải `from . import data`**, đã sửa lại cho đúng cú pháp thật sau
red-team) vẫn phải resolve đúng tới `data.py`, KHÔNG bị nhầm sang thư mục `data/`. **Đây là
suy luận theo spec Python, PHẢI verify bằng lệnh chạy thật
(`python3.10 -c "from app import data; print(data.__file__)"`) sau khi tạo thư mục — không
chỉ tin lý thuyết.** Nếu verify thất bại (Python resolve nhầm), phải đổi tên thư mục (vd
`app/storage_data/`) — đây là fallback đã cân nhắc nhưng KHÔNG chọn làm phương án chính vì
user đã chọn `app/data/`.
`[Red team — Accept, Finding "app/__pycache__ not cleared before verify + no rollback path"]`
**BỔ SUNG:** xoá `app/__pycache__/` trước khi chạy lệnh verify này (bytecode cache cũ có thể
che giấu lỗi import thật). Nếu verify FAIL, KHÔNG tự ý đổi tên thư mục ngay — dừng lại, báo
cáo lỗi cụ thể cho user quyết định (đổi tên `app/storage_data/` hay hướng khác), vì đây là
quyết định đặt tên đã chốt với user trước đó, không tự ý đảo ngược.

## Cấu trúc đích

```
app/
├── data.py                    (module code, KHÔNG đổi — danh mục dịch vụ/nha sĩ)
├── data/                      (thư mục MỚI — chỉ chứa data file runtime)
│   ├── appointments.json      (từ app/appointments.json)
│   ├── device_tokens.json     (từ app/device_tokens.json)
│   ├── audit_log.jsonl        (từ app/audit_log.jsonl)
│   └── outbox/
│       └── push_outbox.jsonl  (từ app/outbox/push_outbox.jsonl)
├── storage.py                 (sửa APPOINTMENTS_PATH, TOKENS_PATH)
├── safety.py                  (sửa AUDIT_LOG_PATH)
├── push.py                    (sửa OUTBOX_DIR/OUTBOX_PATH)
└── ...(các file .py khác không đổi)
```

## Path constant cần sửa (xác nhận qua scout, PHẢI đọc lại số dòng thật trước khi sửa)

- `app/storage.py:30-32`: `_BASE = os.path.dirname(__file__)` →
  `_BASE = os.path.join(os.path.dirname(__file__), "data")`. `APPOINTMENTS_PATH`/
  `TOKENS_PATH` dùng lại `_BASE`, không cần sửa riêng từng dòng.
- `app/safety.py:19`: `AUDIT_LOG_PATH = os.path.join(os.path.dirname(__file__),
  "audit_log.jsonl")` → thêm `"data"` vào giữa:
  `os.path.join(os.path.dirname(__file__), "data", "audit_log.jsonl")`.
- `app/push.py:26-27`: `OUTBOX_DIR = os.path.join(os.path.dirname(__file__), "outbox")` →
  `os.path.join(os.path.dirname(__file__), "data", "outbox")`. `OUTBOX_PATH` dùng lại
  `OUTBOX_DIR`, không cần sửa riêng.

## Không cần sửa (đã xác nhận qua scout — "tình cờ đúng" hoặc không liên quan)

- `scripts/migrate_to_supabase.py`, `scripts/clean_stale_appointments.py`: dùng lại
  `storage.APPOINTMENTS_PATH`/`storage.list_appointments()`, tự động đúng khi
  `storage.py` sửa xong — KHÔNG cần sửa file này.
- `tests/test_storage.py`, `tests/test_safety.py`: monkeypatch `storage.APPOINTMENTS_PATH`/
  `TOKENS_PATH`/dùng `tmp_path` riêng — KHÔNG phụ thuộc vị trí thật, KHÔNG cần sửa.
- `tests/test_reminder_worker.py`: mock dict trả về, không liên quan filesystem path —
  KHÔNG cần sửa.
- `.gitignore`: chỉ có dòng bare `outbox/` (không anchor `/app/outbox/`) — pattern này khớp
  `app/data/outbox/` ở MỌI cấp độ theo git ignore semantics, KHÔNG cần sửa NỘI DUNG file.
  `[Red team — Accept, Finding ".gitignore outbox/ framing incomplete — git mv is mandatory not just history-preserving"]`
  **LƯU Ý quan trọng:** `push_outbox.jsonl` hiện ĐANG được git track dù khớp pattern
  `outbox/` (file đã track từ trước thì `.gitignore` không tự động untrack nó). Do đó
  `git mv` cho file này KHÔNG chỉ là "để giữ lịch sử" — nó là bước BẮT BUỘC để giữ file tiếp
  tục được track sau khi dời (dùng `mv` thường + không `git add` sẽ khiến file biến mất
  khỏi git tracking vì path mới khớp ignore pattern). Verify lại bằng `git status` sau khi
  dời — file mới phải xuất hiện dạng `renamed:`/`R`, không phải bị bỏ track.

## Cross-reference cần sửa (docs/prose, không phải code — 15+ vị trí xác nhận qua scout)

`README.md`, `docs/codebase-summary.md`, `docs/system-architecture.md`,
`docs/database-storage-guide.md`, `docs/getting-started-guide.md`, `docs/BAOCAO_DOAN.md`,
`docs/BAOCAO_DANHGIA.md`, `docs/project-roadmap.md`, `docs/eval/rubric.md`,
`mobile/README.md` (lưu ý path `../outbox/push_outbox.jsonl` viết theo góc nhìn từ
`mobile/`, cần tính lại độ sâu), `app/booking.py:5` (docstring prose, không phải import).
`docs/hoc/05-push.md`, `docs/hoc/08-storage-calendar-reminder.md` mention các path này CHỈ
làm ví dụ minh hoạ giảng dạy — theo tinh thần các plan trước (không viết lại nội dung giảng
dạy ngoài phạm vi cần thiết), CHỈ sửa nếu prose mô tả path THẬT (không phải ví dụ code block
minh hoạ chung chung) — đọc kỹ từng chỗ trước khi quyết định sửa hay để nguyên.

`[Red team — Accept, Finding "mobile/README.md baseline mischaracterized"]`
**SỬA LẠI mô tả cho đúng (2 reviewer độc lập cùng bắt):** `mobile/README.md:42` hiện ghi
`../outbox/push_outbox.jsonl` — path này **ĐÃ SAI TỪ TRƯỚC** (thiếu segment `app/`, không
phải "chỉ cần tính lại độ sâu tương đối" như plan mô tả ban đầu). `mobile/` và `app/` là 2
thư mục ANH EM ở gốc repo, nên `../outbox/...` từ `mobile/README.md` trỏ tới
`<gốc repo>/outbox/...` (không tồn tại), không phải `app/outbox/...` thật. Đây là bug có
sẵn TRƯỚC plan này, không phải do việc dời file gây ra. Target đúng SAU khi dời (không đổi
so với draft ban đầu): `../app/data/outbox/push_outbox.jsonl` (1 cấp lên từ `mobile/` ra
gốc, rồi vào `app/data/outbox/`).

`[Red team — Accept, Finding "scripts/migrate_to_supabase.py docstring omitted"]`
**BỔ SUNG:** `scripts/migrate_to_supabase.py:2` có docstring nhắc `appointments.json,
device_tokens.json` (bare, không phải import — code đã dùng đúng
`storage.APPOINTMENTS_PATH`/`TOKENS_PATH`) — docstring này cần sửa cho nhất quán, dù code
không cần đổi.

`[Red team — Accept, Finding "docs/BAOCAO_DOAN.md:198 false-positive scope line"]`
**SỬA:** `docs/BAOCAO_DOAN.md:198` (trong danh sách cross-reference cần sửa) thực tế là
prose chung ("JSONL — audit log, outbox push, dataset đánh giá"), KHÔNG có path cụ thể nào
để sửa — bỏ dòng 198 khỏi checklist thao tác, chỉ giữ lại dòng 166 và 282-284 của file này
(có path cụ thể thật).

## Phases

| Phase | Name | Phụ thuộc | File(s) touched |
|-------|------|-----------|------------------|
| 1 | [Move Data Files And Update Path Constants](./phase-01-move-data-files-and-update-path-constants.md) | Không | `app/*.json`+`app/audit_log.jsonl`+`app/outbox/`→`app/data/`, `storage.py`, `safety.py`, `push.py`, verify `.gitignore`, pre-flight kill stray process |
| 2 | [Update Docs And Cross References](./phase-02-update-docs-and-cross-references.md) | Phase 1 | `README.md`, `docs/*.md` (9 file, trừ `BAOCAO_DOAN.md:198` không cần sửa), `mobile/README.md`, `app/booking.py` (docstring), `scripts/migrate_to_supabase.py` (docstring) |

**Phase 1 PHẢI xong trước Phase 2** (Phase 2 chỉ sửa prose, không có code — không cần chạy
song song thật sự vì Phase 1 đã bao trọn toàn bộ rủi ro kỹ thuật; giữ 2 phase để tách rõ
"đổi hành vi" (Phase 1) khỏi "cập nhật tài liệu" (Phase 2), không phải vì cần chạy song
song).

## Test Infrastructure (TDD cho pure refactor)

**Red (baseline, chạy TRƯỚC khi sửa):**
`[Red team — Accept, Finding "stale running Flask process can silently recreate empty data files mid-migration"]`
- **Pre-flight bắt buộc:** kiểm tra và kill mọi process Flask/worker đang chạy sẵn từ
  session trước (`ps aux | grep -i "app.app\|reminder_worker"` hoặc tương tự) TRƯỚC khi bắt
  đầu dời file — `app.py` chạy `debug=True` (Werkzeug reloader), reloader này CHỈ theo dõi
  file `.py`, KHÔNG theo dõi data file. Nếu có process cũ còn sống giữ path constant cũ, nó
  có thể ghi audit log/lưu appointment vào path CŨ ngay giữa lúc `git mv` đã xong nhưng
  path constant .py chưa kịp sửa (do reloader chưa reload) — tạo file rỗng mới âm thầm ở vị
  trí cũ, y hệt bug pattern chính plan này đang cố tránh.
- `python3.10 -m pytest tests/ -v` → ghi lại số liệu chính xác (kỳ vọng 92 passed, 1
  skipped, khớp baseline mọi plan trước).
- Đếm số lịch hẹn thật trong `app/appointments.json` (`python3.10 -c "import json;
  print(len(json.load(open('app/appointments.json'))))"`) — dùng làm baseline so khớp
  CHÍNH XÁC sau khi dời (không chỉ "len > 0").
- Khởi động thử `python3.10 -m app.app` (kill sau khi xác nhận start OK), curl `/api/start`
  → xác nhận hành vi baseline TRƯỚC khi đổi path.

**Green (sau khi dời + sửa path, verify lại CHÍNH XÁC khớp baseline):**
- `python3.10 -m pytest tests/ -v` → phải khớp 100% baseline (92 passed, 1 skipped).
- Đếm lại số lịch hẹn trong `app/data/appointments.json` — PHẢI khớp CHÍNH XÁC số ở bước
  Red (không phải "vẫn > 0").
- `python3.10 -m app.app`, curl `/api/start` → xác nhận vẫn hoạt động, không tạo file rỗng
  mới ở vị trí cũ (`app/appointments.json` không được tồn tại lại sau khi chạy).
- `python3.10 -c "from app import data; print(data.__file__)"` → xác nhận resolve đúng
  `app/data.py`, KHÔNG bị nhầm sang thư mục `app/data/` (xem rủi ro đặt tên ở trên).

`[Red team — Accept, Finding "no interruption/rollback state-check gate"]`
**Gate khi resume sau gián đoạn:** nếu quá trình thực hiện Phase 1 bị ngắt giữa chừng (vd
hết context, lỗi tool), TRƯỚC khi resume PHẢI chạy `git status --short app/` để xác nhận
trạng thái hiện tại — nếu thấy `git mv` đã xong (file ở `app/data/`) nhưng `storage.py`/
`safety.py`/`push.py` CHƯA sửa (hoặc ngược lại), ĐÂY LÀ TRẠNG THÁI HALF-MIGRATED NGUY HIỂM —
sửa nốt phần path constant còn thiếu NGAY LẬP TỨC trước khi làm bất kỳ việc gì khác (kể cả
chạy app để "kiểm tra thử"), không được để trạng thái này tồn tại qua bất kỳ lệnh chạy app
nào.

`[Red team — Accept, Finding "pytest dirties audit_log/outbox files, no cleanup before final git status"]`
**Dọn dẹp sau pytest:** `python3.10 -m pytest tests/ -v` VÀ việc chạy `python3.10 -m app.app`
để verify HTTP có thể ghi entry thật vào `app/data/audit_log.jsonl`/
`app/data/outbox/push_outbox.jsonl` (side-effect quen thuộc đã gặp ở 2 plan trước). TRƯỚC
khi chạy `git status` xác nhận cuối cùng, PHẢI `git checkout -- app/data/audit_log.jsonl
app/data/outbox/push_outbox.jsonl` (nếu 2 file này đã có nội dung tracked trước đó) để
tránh lẫn giữa diff thao tác dời file thật với nhiễu do chạy test/verify.

## Red Team Review

### Session — 2026-07-10
**Findings:** 10 unique sau dedupe (từ 2 reviewer: Security Adversary/Fact Checker,
Assumption Destroyer/Scope Auditor — 1 finding High được **2 reviewer độc lập cùng bắt**:
`mobile/README.md` baseline mischaracterized).
**Severity breakdown:** 1 Critical, 2 High, 7 Medium.
**Kết quả:** 10 finding Accept, 1 finding Reject (thông tin, không phải bug do plan gây ra).

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| 1 | Process Flask/worker cũ còn sống (Werkzeug reloader không theo dõi data file) có thể ghi đè âm thầm vào path cũ giữa lúc dời | Critical | Accept | Phase 1 (Bước 0 mới) |
| 2 | Không có gate kiểm tra trạng thái nếu bị gián đoạn giữa `git mv` và sửa path constant | High | Accept | Phase 1 (Bước 2), plan.md Test Infrastructure |
| 3 | `mobile/README.md` baseline mô tả sai — text hiện tại đã sai từ trước (thiếu `app/`), không phải "chỉ cần tính lại độ sâu" | High | **2 reviewer độc lập cùng bắt** — Accept | plan.md, Phase 2 |
| 4 | `.gitignore` `outbox/` — chưa giải thích rõ `git mv` là bắt buộc (không chỉ giữ lịch sử) vì file track dù khớp ignore pattern | Medium | Accept | plan.md, Phase 1 (Bước 2) |
| 5 | Grep sweep Bước 6 bỏ sót `eval/*.py` | Medium | Accept | Phase 1 (Bước 6) |
| 6 | Verify import không xoá `__pycache__` trước, không có hướng dẫn khi FAIL | Medium | Accept | Phase 1 (Green verify) |
| 7 | PII/audit-log exposure preserved bởi `git mv` (không thay đổi mức lộ) | Medium | **Reject** | — |
| 8 | `scripts/migrate_to_supabase.py:2` docstring bị bỏ sót khỏi Phase 2 | Medium | Accept | Phase 2 |
| 9 | Plan mô tả sai cú pháp import thật (`from . import data` thay vì `from .data import NAME`) | Medium | Accept | plan.md |
| 10 | `docs/BAOCAO_DOAN.md:198` false-positive, không có path cụ thể để sửa | Medium | Accept | Phase 2 |
| 11 | pytest/verify HTTP làm bẩn `audit_log.jsonl`/`outbox/` mới, chưa có bước dọn trước `git status` cuối | Medium | Accept | Phase 1 (Green verify) |

**Rationale reject #7:** dữ liệu PII (tên bệnh nhân, nội dung hội thoại) đã tồn tại trong
lịch sử git TRƯỚC plan này — `git mv` giữ nguyên lịch sử, không làm tăng hay giảm mức độ lộ
dữ liệu. Đây là tình trạng có sẵn của repo, ngoài phạm vi plan "dời file cho gọn", không có
hành động cụ thể nào cần làm trong plan này.

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01, phase-02 (toàn bộ, sau khi áp dụng 10 finding accept).
- Decision deltas checked: 10 (thêm Bước 0 pre-flight kill process; thêm gate resume sau
  gián đoạn; sửa lại mô tả `mobile/README.md` từ "tính lại độ sâu" thành "sửa bug có sẵn";
  làm rõ `.gitignore`/`git mv` bắt buộc; mở rộng grep sang `eval/*.py`; thêm xoá
  `__pycache__` trước verify; thêm `scripts/migrate_to_supabase.py` vào Phase 2 scope; sửa
  cú pháp import mô tả sai trong plan.md; loại `docs/BAOCAO_DOAN.md:198` khỏi checklist;
  thêm bước `git checkout --` dọn audit_log/outbox trước git status cuối).
- Reconciled stale references: 1 (Phase 2's "11 file" đếm gốc — cập nhật thành "11 file gốc
  + `scripts/migrate_to_supabase.py` bổ sung, trừ `BAOCAO_DOAN.md:198`" cho khớp số liệu
  thật ở Success Criteria).
- Unresolved contradictions: 0.

## Dependencies

Không phụ thuộc plan khác đang mở. Không blocked bởi plan nào trong `plans/`.

## Acceptance Criteria (toàn plan)

- [x] `app/data/appointments.json`, `app/data/device_tokens.json`,
  `app/data/audit_log.jsonl`, `app/data/outbox/push_outbox.jsonl` tồn tại; vị trí cũ
  (`app/appointments.json`, `app/device_tokens.json`, `app/audit_log.jsonl`,
  `app/outbox/`) KHÔNG còn.
- [x] `storage.py`, `safety.py`, `push.py` path constant trỏ đúng `app/data/`, verify bằng
  chạy thật (không chỉ đọc code).
- [x] Số lịch hẹn/token trong `app/data/appointments.json`/`device_tokens.json` khớp CHÍNH
  XÁC baseline (không bị tạo file rỗng mới, không mất dữ liệu).
- [x] `from app import data` vẫn resolve đúng `app/data.py` (verify bằng lệnh chạy thật).
- [x] `git status` xác nhận dùng `git mv` cho toàn bộ thao tác dời file (giữ lịch sử), file
  mới trong `app/data/outbox/` không bị git track nhầm nếu đáng lẽ phải bị ignore (đối
  chiếu với hành vi TRƯỚC khi dời — `push_outbox.jsonl` có đang track hay bị ignore).
- [x] `python3.10 -m pytest tests/ -v` khớp 100% baseline (92 passed, 1 skipped).
- [x] `python3.10 -m app.app` khởi động OK, `/api/start` trả về HTTP 200 (verify bằng
  curl thật).
- [x] Toàn bộ cross-reference doc/prose đã liệt kê được cập nhật, verify bằng đọc lại nội
  dung thật (không chỉ tin theo checklist viết sẵn).
- [x] KHÔNG đổi bất kỳ hành vi nghiệp vụ nào — chỉ đổi vị trí file + path constant.
- [x] Không có process Flask/worker cũ nào còn sống từ trước khi bắt đầu (đã kill trước khi
  dời file).
- [x] `scripts/migrate_to_supabase.py` docstring đã cập nhật (dù code không cần đổi).
