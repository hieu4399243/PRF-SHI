---
title: "Consolidate docs into docs/ folder and remove unused files"
description: "Gộp toàn bộ .md (trừ README.md gốc và plans/) vào docs/, dời eval/rubric.md + eval/results.md vào docs/eval/, hoc/*.md vào docs/hoc/, BAOCAO_*.md vào docs/. Xoá release-manifest.json (release-manifest.json không dùng)."
status: completed
priority: P2
branch: "main"
tags: ["docs", "cleanup", "tdd"]
blockedBy: []
blocks: []
created: "2026-07-10T06:33:04.399Z"
createdBy: "ck:plan"
source: skill
---

# Consolidate docs into docs/ folder and remove unused files

## Overview

Gộp toàn bộ file `.md` rải rác (trừ `README.md` gốc và `plans/` — loại trừ theo quyết định
user) vào `docs/`. Xoá file không dùng đến (`release-manifest.json`).

**Quyết định đã chốt với user:**
1. Gộp TẤT CẢ `.md` (trừ `README.md`, `plans/`) vào `docs/` — bao gồm `hoc/*.md` (10 bài),
   `eval/*.md` (2 file), `BAOCAO_DOAN.md`, `BAOCAO_DANHGIA.md`.
2. Xoá `release-manifest.json` (366KB, không script/doc nào tham chiếu).
   `[Red team — Accept, Finding "release-manifest.json vs .repomixignore deletion scope"]`
   **QUYẾT ĐỊNH ĐÃ SỬA sau red-team:** `.repomixignore` KHÔNG bị xoá — 2 reviewer độc lập
   tìm bằng chứng nó ĐANG được dùng thật (`.claude/agents/docs-manager.md`,
   `.claude/agents/debugger.md` gọi `repomix` trực tiếp; nó che `docs/*`, `plans/*`,
   `tests/*` mà `.gitignore` không che — xoá sẽ khiến lần chạy `repomix` tiếp theo nuốt
   nhầm `docs/`/`plans/`/`tests/` vào manifest). User xác nhận giữ lại.
3. `mobile/README.md` GIỮ NGUYÊN (không thuộc phạm vi "docs rải rác" — đây là README riêng
   của package mobile, đúng quy ước 1 subproject có README riêng, không phải tài liệu chung
   của dự án).

## Cấu trúc đích

```
docs/
├── (7 file .md hiện có, không đổi tên)
├── BAOCAO_DOAN.md          (từ gốc)
├── BAOCAO_DANHGIA.md       (từ gốc)
├── hoc/                    (10 bài, từ hoc/ gốc)
│   ├── 00-muc-luc.md
│   └── ...
└── eval/
    ├── rubric.md           (từ eval/rubric.md)
    └── results.md          (từ eval/results.md — file DO eval/evaluate.py TỰ SINH)
```
`eval/` (thư mục gốc) vẫn còn — chỉ mất 2 file `.md`, giữ nguyên `evaluate.py`,
`dataset.jsonl`, `dataset_complex.jsonl` (không phải doc, là data/code).

## 1 rủi ro kỹ thuật ẩn đã phát hiện qua scout (PHẢI xử lý, không phải optional)

**`eval/evaluate.py` tự ghi `eval/results.md` qua `os.path.dirname(__file__)`**
(`RESULTS_PATH = os.path.join(os.path.dirname(__file__), "results.md")`) — CÙNG LOẠI lỗi
tiềm ẩn đã gặp ở plan restructure `app/` trước (path gắn theo vị trí script). Nếu dời
`results.md` vào `docs/eval/` mà KHÔNG sửa `RESULTS_PATH`, lần chạy `evaluate.py` tiếp theo
sẽ ghi 1 file MỚI vào `eval/results.md` (vị trí cũ), trong khi bản "chính thức" nằm ở
`docs/eval/results.md` không được cập nhật — 2 bản sẽ lệch nhau âm thầm.
**Fix: sửa `RESULTS_PATH` trong `eval/evaluate.py` trỏ thẳng tới
`docs/eval/results.md`** (không dùng `os.path.dirname(__file__)` nữa cho hằng số này, vì
`evaluate.py` KHÔNG di chuyển — chỉ output của nó di chuyển).

## Link nội bộ trong file bị dời cần tính lại độ sâu tương đối

- **6 bài `hoc/*.md`** (`01`, `02`, `04`, `05`, `06`, `07`) có link tới file code, dạng
  `[triage.py](../app/triage.py)` (1 cấp lên từ `hoc/`, rồi vào `app/`). Sau khi dời
  `hoc/*.md` → `docs/hoc/`, cần THÊM 1 CẤP: `[triage.py](../../app/triage.py)`.
- **`hoc/08-storage-calendar-reminder.md`** có link
  `[DATABASE.md](../docs/database-storage-guide.md)` (1 cấp lên rồi vào `docs/`). Sau khi
  dời, `docs/database-storage-guide.md` trở thành ANH EM CÙNG CẤP của `docs/hoc/` (không
  phải phải đi vào `docs/` nữa vì đã Ở TRONG `docs/`) → sửa thành
  `[DATABASE.md](../database-storage-guide.md)` (1 cấp lên từ `docs/hoc/` tới `docs/`, không
  còn `docs/` trong path).
- **Link GIỮA các bài `hoc/` với nhau** (trong `hoc/00-muc-luc.md`, dạng bare
  `01-viet-triage-tu-dau.md`) — GIỮ NGUYÊN không đổi, vì tất cả cùng dời tới `docs/hoc/`,
  vẫn cùng thư mục với nhau.
- **`docs/project-roadmap.md`** và **`docs/project-overview-pdr.md`** hiện có link
  `[BAOCAO_DANHGIA.md](../BAOCAO_DANHGIA.md)` (1 cấp lên từ `docs/` rồi ra gốc). Sau khi dời
  `BAOCAO_DANHGIA.md` vào `docs/`, nó trở thành ANH EM CÙNG CẤP → sửa thành
  `[BAOCAO_DANHGIA.md](BAOCAO_DANHGIA.md)` (không còn `../`).
- **Bên trong `BAOCAO_DOAN.md`/`BAOCAO_DANHGIA.md`**: các mention dạng prose (không phải
  link markdown) như `eval/results.md`, `eval/rubric.md`, `hoc/` — GIỮ NGUYÊN text (trùng
  hợp: cả 2 file này VÀ `eval/`/`hoc/` đều dời vào `docs/`, nên đường dẫn TƯƠNG ĐỐI từ
  `docs/BAOCAO_DOAN.md` tới `docs/eval/results.md` vẫn là `eval/results.md`, không đổi).
  KHÔNG cần sửa các mention này — chỉ VERIFY lại bằng mắt sau khi dời, không sửa mù.
  `[Red team — Accept, Finding "BAOCAO prose mentions of eval/evaluate.py miscategorized"]`
  **NGOẠI LỆ:** những câu nhắc `eval/evaluate.py` (script, KHÔNG di chuyển, ở lại `eval/`
  gốc) CÙNG câu với `eval/results.md`/`eval/rubric.md` (đã dời) — path đúng cho
  `evaluate.py` từ `docs/BAOCAO_*.md` phải là `../eval/evaluate.py` (đi RA NGOÀI `docs/`),
  khác với 2 file kia. Xử lý riêng, không gộp chung "không cần sửa".
  `[Red team — Accept, Finding "BAOCAO_DOAN.md sơ đồ cây thư mục stale"]`
  **BỔ SUNG:** `BAOCAO_DOAN.md` có sơ đồ cây thư mục ASCII (mô tả cấu trúc repo) liệt kê
  `eval/results.md`, `eval/rubric.md` như con của `eval/` gốc — SAI sau khi dời (bug cùng
  loại đã bị bắt và fix ở plan `restructure-app-package` trước, xem
  `plans/260710-1059-restructure-app-package/plan.md` Red Team finding #3). Sơ đồ này PHẢI
  cập nhật để khớp cấu trúc mới, không thuộc diện "giữ nguyên prose".
  `[Red team — Accept, Finding "hoc/00,01,03,09 scratch-file/shell-command refs not covered"]`
  **BỔ SUNG:** `hoc/00-muc-luc.md`, `hoc/01-viet-triage-tu-dau.md`, `hoc/03-safety.md`,
  `hoc/09-admin.md` chứa LỆNH SHELL và prose hướng dẫn học viên tạo file thực hành ngay
  trong `hoc/` (vd `touch hoc/triage_demo.py`, `python hoc/triage_demo.py`,
  `hoc/audit_demo.jsonl`) — 4 file này KHÔNG nằm trong danh sách "6 bài có link app/*.py"
  ở Phase 1 nên bị bỏ sót hoàn toàn. Lưu ý: quy tắc "bare `hoc/...md` tình cờ đúng sau khi
  dời" CHỈ áp dụng cho LINK MARKDOWN (resolve tương đối theo file chứa nó) — KHÔNG áp dụng
  cho LỆNH SHELL (resolve theo CWD lúc chạy, thường là gốc repo). Quyết định đã chốt với
  user: đổi toàn bộ tham chiếu `hoc/` trong lệnh shell/prose của 4 file này thành
  `docs/hoc/`, giữ nguyên quy ước "file thực hành nằm cùng thư mục bài học".

## Phases

| Phase | Name | Phụ thuộc | File(s) touched |
|-------|------|-----------|------------------|
| 1 | [Move Docs And Fix Internal Links](./phase-01-move-docs-and-fix-internal-links.md) | Không | `hoc/*.md`→`docs/hoc/` (10 bài + 4 bài có ref shell/prose bổ sung), `eval/*.md`→`docs/eval/`, `BAOCAO_*.md`→`docs/` (+ sơ đồ cây + prose `evaluate.py`), `eval/evaluate.py` (path fix), xoá `release-manifest.json` |
| 2 | [Update README And Codebase Summary](./phase-02-update-readme-and-codebase-summary.md) | Phase 1 | `README.md`, `docs/codebase-summary.md` |
| 3 | [Update Getting Started And Roadmap Docs](./phase-03-update-getting-started-and-roadmap-docs.md) | Phase 1 | `docs/getting-started-guide.md`, `docs/project-roadmap.md`, `docs/project-overview-pdr.md` |

`[Red team — Accept, Finding "No explicit gate confirming Phase 1 fully committed before Phase 2/3"]`
**Phase 1 PHẢI xong trước — Phase 2 và 3 chạy song song sau đó** (đều phụ thuộc cấu trúc
`docs/` mới đã tồn tại, nhưng không đụng file của nhau). **Gate bắt buộc:** trước khi bắt
đầu Phase 2/3, xác nhận TOÀN BỘ Success Criteria của Phase 1 đã pass VÀ `git status` sạch
(không còn thao tác `git mv`/`git rm` dang dở) — nếu Phase 2/3 đọc file lúc cây thư mục
đang ở trạng thái lẫn lộn cũ/mới, kết quả phân loại link "tình cờ đúng hay sai" sẽ sai.

## Test Infrastructure (TDD cho refactor tài liệu)

Đây chủ yếu là dời file + sửa link — không có test tự động cho nội dung markdown. Áp dụng
TDD cho phần CÓ code thay đổi (Phase 1's fix `eval/evaluate.py`): **Red** = chạy
`eval/evaluate.py` TRƯỚC khi sửa, xác nhận ghi vào `eval/results.md` (vị trí cũ). **Green**
= sau khi sửa + dời, chạy lại, xác nhận ghi đúng `docs/eval/results.md`, và `eval/results.md`
(vị trí cũ) KHÔNG bị tạo lại. Cho các file `.md` thuần (không phải code), verify bằng cách
đọc lại + kiểm tra link markdown resolve đúng (không có test tự động, xem Risk Assessment
từng phase).

`[Red team — Accept, Finding "TDD re-run of evaluate.py overwrites non-deterministic timing content"]`
**NGOẠI LỆ quan trọng:** `eval/results.md` chứa cột "Thời gian TB (ms/câu)" — số liệu PHỤ
THUỘC THỜI ĐIỂM CHẠY (không cố định). Chạy lại `evaluate.py` như bước Green ở trên SẼ làm
nội dung `results.md` khác bản gốc — đây là hành vi CHỦ Ý của bước Green (xác nhận path fix
hoạt động thật), KHÔNG vi phạm "không viết lại nội dung .md nào" ở Acceptance Criteria toàn
plan (điều khoản đó áp dụng cho các file bị DỜI, không áp dụng cho file DO CHÍNH SCRIPT
TRONG PLAN NÀY tự sinh ra như một phần của việc verify path fix). Không cần khôi phục lại
nội dung `results.md` bản cũ sau khi verify xong.

Kế thừa từ các plan trước: full test suite `python3.10 -m pytest tests/ -v` phải vẫn pass
92/93 (không có phase nào trong plan này đụng `app/`/`tests/`, nhưng verify lại 1 lần ở
Phase 1 để chắc chắn việc xoá/dời file không ảnh hưởng gì ngoài dự kiến).

## Red Team Review

### Session — 2026-07-10
**Findings:** 13 unique sau dedupe (từ 3 reviewer: Security Adversary/Fact Checker,
Failure Mode Analyst/Flow Tracer, Assumption Destroyer/Scope Auditor — 2 finding Critical
và 1 finding High được **2 reviewer độc lập cùng bắt**, tín hiệu mạnh).
**Severity breakdown:** 2 Critical, 2 High, 8 Medium, 1 Reject.
**Kết quả:** 12 finding Accept (2 finding đụng quyết định user đã chốt trước — hỏi lại qua
`AskUserQuestion`, user xác nhận đảo ngược quyết định `.repomixignore` và chọn hướng xử lý
scratch-file convention), 1 finding Reject (không có fix cụ thể khả thi hơn, giữ nguyên vì
YAGNI).

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| 1 | `hoc/00,01,03,09` có lệnh shell/prose tham chiếu `hoc/` không thuộc phạm vi "6 bài có link app/*.py" — bị bỏ sót hoàn toàn | Critical | Accept | Phase 1 (Bước 6) |
| 2 | `BAOCAO_DOAN.md` có sơ đồ cây thư mục ASCII stale sau khi dời, không thuộc diện "giữ nguyên prose" | Critical | Accept | Phase 1 (Bước 7) |
| 3 | TDD Red/Green chạy lại `evaluate.py` ghi đè cột "Thời gian TB" trong `results.md`, mâu thuẫn tiêu chí "không viết lại nội dung .md" | High | Accept | plan.md (Test Infrastructure — thêm ngoại lệ) |
| 4 | Xoá `.repomixignore` — bằng chứng nó đang được `docs-manager`/`debugger` agent dùng thật, không phải "mồ côi" | High | Accept (đảo ngược quyết định user, đã hỏi lại và được xác nhận) | plan.md Overview, Phase 1 Bước 5 |
| 5 | `.repomixignore` "unused" bị `release-manifest.json` tự mâu thuẫn (liệt kê chính nó) | Medium | Accept (gộp vào #4) | Phase 1 Bước 5 |
| 6 | BAOCAO prose mention `eval/evaluate.py` bị gộp nhầm cùng nhóm "không cần sửa" với `eval/results.md`/`eval/rubric.md` — path đúng khác nhau | Medium | Accept | plan.md, Phase 1 Bước 7 |
| 7 | `README.md` dòng lệnh+comment lẫn lộn, dễ bị bỏ sót khi áp dụng máy móc quy tắc "lệnh không đổi" | Medium | Accept | Phase 2 |
| 8 | Phase 3 đếm thiếu 1 chỗ mention `hoc/triage_demo.py` (nói "1 câu", thực tế 2) | Medium | Accept | Phase 3 |
| 9 | Thiếu gate xác nhận Phase 1 hoàn tất + `git status` sạch trước khi chạy Phase 2/3 song song | Medium | Accept | plan.md Phases section |
| 10 | Verify link chỉ test theo danh sách viết cứng trong phase file, không đọc nội dung thật đã sửa — có thể bỏ sót lỗi gõ path | Medium | Accept | Phase 1 Bước 6 verify |
| 11 | Thiếu grep hậu-kiểm `eval/evaluate.py` sau khi sửa (chỉ có test hành vi, không có test static) | Medium | Accept | Phase 1 Bước 6 verify |
| 12 | `git mv eval/results.md` giả định file đã track, không có precheck | Medium | Accept | Phase 1 Bước 1 |
| 13 | `RESULTS_PATH` hardcode `docs/eval/results.md` chỉ "dời" chứ không "xoá hẳn" anti-pattern path-coupling | Medium | **Reject** | — |

**Rationale reject #13:** không có fix cụ thể tốt hơn được đề xuất; hardcode absolute path
(qua biến `ROOT` có sẵn) là cách chuẩn đã dùng trong plan `restructure-app-package` trước
(`storage.APPOINTMENTS_PATH`) — thêm 1 tầng config/indirection cho 1 file kết quả duy nhất
là over-engineering, vi phạm YAGNI. Rủi ro thật (silent data loss nếu path sai) đã được
loại bỏ hoàn toàn bởi fix hiện tại.

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01, phase-02, phase-03 (toàn bộ, sau khi áp dụng 12 finding
  accept).
- Decision deltas checked: 12 (`.repomixignore` đảo từ "xoá" sang "giữ nguyên" — cập nhật
  frontmatter description, Overview, Acceptance Criteria, Phase 1 Bước 5 + Related Files +
  Success Criteria + Risk Assessment; thêm 4 file `hoc/00,01,03,09` vào phạm vi Phase 1;
  thêm bước sửa sơ đồ cây `BAOCAO_DOAN.md` + prose `evaluate.py`; thêm ngoại lệ timing
  metric ở Test Infrastructure; thêm gate Phase1→Phase2/3; thêm precheck `git ls-files`;
  thêm grep hậu-kiểm `evaluate.py`; sửa số lượng mention `triage_demo.py` ở Phase 3 từ 1
  thành 2; thêm lưu ý dòng lẫn lộn lệnh+comment ở Phase 2; thêm verify-từ-nội-dung-thật ở
  Phase 1).
- Reconciled stale references: 1 (frontmatter `description` và Overview vẫn ghi "xoá
  release-manifest.json + .repomixignore" — đã sửa khớp quyết định mới ở cả 2 chỗ).
- Unresolved contradictions: 0.

## Dependencies

Không phụ thuộc plan khác đang mở. Không blocked bởi plan nào trong `plans/`.

## Acceptance Criteria (toàn plan)

- [x] `docs/hoc/` (10 file), `docs/eval/` (2 file), `docs/BAOCAO_DOAN.md`,
  `docs/BAOCAO_DANHGIA.md` tồn tại, dùng `git mv` (giữ lịch sử).
- [x] `hoc/`, `eval/rubric.md`, `eval/results.md`, `BAOCAO_DOAN.md`, `BAOCAO_DANHGIA.md`
  KHÔNG còn ở vị trí cũ (đã dời hoàn toàn, không trùng lặp).
- [x] `release-manifest.json` đã bị xoá (`git rm`). `.repomixignore` GIỮ NGUYÊN (quyết định
  đảo ngược sau red-team — vẫn đang được `docs-manager`/`debugger` agent dùng thật).
- [x] `eval/evaluate.py` ghi đúng `docs/eval/results.md`, verify bằng cách CHẠY THẬT.
- [x] Mọi link markdown liên quan (nội bộ trong file dời + cross-reference từ file khác)
  resolve đúng — verify bằng cách đọc lại đường dẫn thủ công hoặc test script kiểm tra file
  đích tồn tại. (Code review độc lập bắt 2 chỗ prose sót — `README.md:43`,
  `docs/codebase-summary.md:54` — đã fix trực tiếp sau review.)
- [x] `README.md` GIỮ NGUYÊN vị trí gốc. `plans/*.md` KHÔNG bị đụng. `mobile/README.md`
  KHÔNG bị đụng.
- [x] `python3.10 -m pytest tests/ -v` vẫn pass 92/93 (không regress từ plan trước).
- [x] KHÔNG viết lại nội dung bất kỳ file `.md` nào — chỉ sửa đường dẫn/link, giữ nguyên
  100% nội dung khác.
