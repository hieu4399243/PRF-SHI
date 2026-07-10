---
phase: 4
title: "Update Root Docs And Entry Commands"
status: pending
priority: P3
dependencies: [1]
---

# Phase 4: Cập nhật `README.md`, `setup.sh`, `docs/*.md` — lệnh chạy + đường dẫn file

## Overview

Sau Phase 1, lệnh chạy app đổi (`python app.py` → `python -m app.app`, tương tự
`reminder_worker.py`), và mọi tài liệu tham chiếu đường dẫn 10 file `.py` ở gốc repo cần cập
nhật sang `app/`. Đây là cập nhật TÀI LIỆU — không đụng code.

**PHỤ THUỘC Phase 1**: cần biết chính xác cấu trúc mới đã tồn tại (không bắt buộc code phải
chạy được, chỉ cần cấu trúc thư mục đã đúng) trước khi viết lại lệnh/đường dẫn.

## Requirements

- Functional: mọi lệnh trong `README.md`/`setup.sh`/`docs/*.md` liên quan tới chạy backend
  phải khớp với cách chạy MỚI (`python -m app.app`, `python -m app.reminder_worker ...`,
  `gunicorn app.app:app`). Mọi đường dẫn file `.py` được nhắc tới (bảng mô tả module, ví dụ
  code, hướng dẫn debug) phải trỏ đúng `app/X.py` thay vì `X.py`.
- Non-functional: KHÔNG viết lại nội dung mô tả NGHIỆP VỤ (vd bảng mô tả "Triage engine —
  Phân loại triệu chứng...") — chỉ sửa ĐƯỜNG DẪN/LỆNH, giữ nguyên mô tả chức năng.

## Architecture

Tìm & thay theo các mẫu sau (áp dụng nhất quán across tất cả file):

| Cũ | Mới |
|---|---|
| `python app.py` | `python -m app.app` |
| `./.venv/bin/python app.py` | `./.venv/bin/python -m app.app` |
| `python reminder_worker.py --watch` | `python -m app.reminder_worker --watch` (tương tự `--once`/`--test`) |
| `gunicorn app:app` | `gunicorn app.app:app` |
| `` `app.py` `` (nhắc tên file trong bảng/mô tả) | `` `app/app.py` `` |
| `` `booking.py` ``/`` `chatbot.py` ``/... (9 file còn lại) | `` `app/booking.py` ``/`` `app/chatbot.py` ``/... |
| `python eval/evaluate.py` | KHÔNG đổi (Phase 3 không đổi lệnh chạy, chỉ đổi import bên
  trong file) |
| `python scripts/....py` | KHÔNG đổi (tương tự) |

## Related Code Files

- Modify: `README.md`
- Modify: `setup.sh`
- Modify: `docs/deployment-guide.md` (đã xác nhận có `gunicorn app:app`, `python app.py`)
- Modify: `docs/getting-started-guide.md`, `docs/database-storage-guide.md`,
  `docs/system-architecture.md`, `docs/code-standards.md`, `docs/codebase-summary.md`,
  `docs/project-overview-pdr.md`, `docs/project-roadmap.md` — CHỈ sửa nếu file đó THỰC SỰ
  tham chiếu đường dẫn/lệnh chạy (đọc từng file, không sửa mù nếu không có gì cần đổi)
- Modify: `.env.example` — **[Red team — Accept, Finding "chỉ kiểm bằng grep, không đọc
  toàn bộ như setup.sh"]** File này NGẮN — ĐỌC TOÀN BỘ (không chỉ dựa vào grep match) trước
  khi kết luận có cần sửa hay không, đối xử như `setup.sh` chứ không phải như 1 file docs
  dài chỉ cần grep.
- Modify: `BAOCAO_DOAN.md`, `BAOCAO_DANHGIA.md` — **[Red team — Accept, Finding "báo cáo
  chấm điểm có sơ đồ thư mục + đường dẫn file gốc, bị bỏ sót khỏi mọi phase — 2 reviewer
  độc lập chỉ ra"]** `BAOCAO_DOAN.md` có bảng phân công công việc + sơ đồ cây thư mục liệt
  kê 10 file `.py` ở gốc — CHỈ sửa đường dẫn/sơ đồ cây cho khớp cấu trúc mới, GIỮ NGUYÊN nội
  dung chấm điểm/phân công/đánh giá (đây là tài liệu nộp bài, không phải chỗ để viết lại nội
  dung).

## Implementation Steps

1. **Grep toàn bộ tham chiếu cần rà soát trước khi sửa** (không đoán file nào cần đổi).
   **[Red team — Accept, Finding "grep cũ thiếu tên data file — README mục 'File sinh ra khi
   chạy' sẽ sai vị trí âm thầm"]** Câu grep PHẢI bao gồm cả tên 4 data file (không chỉ tên
   file `.py`):
   ```bash
   grep -rln "app\.py\|booking\.py\|chatbot\.py\|storage\.py\|safety\.py\|triage\.py\|data\.py\|push\.py\|reminder_worker\.py\|calendar_ics\.py\|gunicorn app:app\|python app\.py\|appointments\.json\|device_tokens\.json\|audit_log\.jsonl\|outbox/" \
     README.md setup.sh docs/*.md .env.example BAOCAO_DOAN.md BAOCAO_DANHGIA.md 2>/dev/null
   ```
   Dùng danh sách file trả về làm checklist CHÍNH XÁC — chỉ sửa những file thật sự có
   match, không sửa file không cần. Đặc biệt chú ý mục "File sinh ra khi chạy" trong
   `README.md` (nhắc `appointments.json`/`audit_log.jsonl` không kèm tiền tố đường dẫn) —
   phải cập nhật thành `app/appointments.json`/`app/audit_log.jsonl`.
2. Với mỗi file trong checklist, đọc kỹ đoạn có match, áp dụng bảng Tìm & Thay ở Architecture
   — phân biệt: (a) lệnh chạy thực sự cần đổi cú pháp, (b) chỉ là TÊN FILE trong bảng mô
   tả/prose cần thêm tiền tố `app/`, (c) KHÔNG đổi (eval/scripts không đổi lệnh).
3. Rà lại `setup.sh` kỹ hơn — đây là SCRIPT THỰC THI, không chỉ tài liệu prose. Đọc toàn bộ
   file để xác nhận không có logic nào khác (vd kiểm tra file tồn tại bằng đường dẫn cũ,
   `test -f app.py`) ngoài 2 dòng `echo` đã grep thấy — nếu có, phải sửa logic đó cho khớp
   cấu trúc mới, không chỉ sửa text hiển thị.
4. Verify thủ công: chạy lại các lệnh MỚI được ghi trong README (`python3.10 -m app.app` ở
   nền, `curl /`, dừng lại) để xác nhận tài liệu khớp thực tế, không chỉ sửa text suông.
5. **[Red team — Accept, Finding "không có bước kiểm tra NGƯỢC — bắt sót (under-correction)"]**
   Sau khi sửa xong TẤT CẢ file trong checklist bước 1, chạy lại CHÍNH CÂU LỆNH GREP đó lần
   NỮA trên đúng các file đã sửa. Với mỗi kết quả còn trả về, đọc lại để xác nhận đây là
   trường hợp CHỦ Ý không đổi (vd trong `eval/evaluate.py`/`scripts/` không đổi lệnh chạy —
   nhưng đó là trong Phase 3, không phải file Phase 4 quản lý) hay là SÓT thật cần sửa tiếp.
   Đặc biệt chú ý `docs/codebase-summary.md` và `docs/system-architecture.md` (nhiều chỗ
   nhắc tên file hơn các file khác) — dễ sót nhất.

## Success Criteria

- [ ] `README.md`, `setup.sh` dùng lệnh chạy mới (`python -m app.app`, `python -m
  app.reminder_worker`), bảng mô tả module trỏ đúng `app/X.py`.
- [ ] `docs/deployment-guide.md` dùng `gunicorn app.app:app`, `python -m app.app`.
- [ ] Các file `docs/*.md` khác: chỉ sửa nếu grep xác nhận có tham chiếu, không sửa mù.
- [ ] `setup.sh` không chỉ sửa text hiển thị — nếu có logic kiểm tra file bằng đường dẫn cũ,
  logic đó cũng phải cập nhật.
- [ ] Lệnh mới trong README thực sự chạy được khi thử thủ công (không chỉ đúng cú pháp trên
  giấy).
- [ ] `BAOCAO_DOAN.md`/`BAOCAO_DANHGIA.md` không còn sơ đồ cây/đường dẫn file gốc lỗi thời,
  nội dung chấm điểm/phân công GIỮ NGUYÊN.
- [ ] `.env.example` đã ĐỌC TOÀN BỘ (không chỉ grep), xác nhận cần sửa hay không.
- [ ] Grep hậu-kiểm (bước 5) chạy lại sau khi sửa, kết quả còn lại đều đã xác nhận là CHỦ Ý
  không đổi, không phải sót.

## Risk Assessment

- **Sửa mù theo bảng Tìm & Thay mà không đọc ngữ cảnh** có thể sửa nhầm chỗ không nên đổi
  (vd đoạn code mẫu trong docs minh hoạ cấu trúc CŨ có chủ đích để so sánh trước/sau, hoặc
  tên biến trùng tên file như `data.py` xuất hiện trong câu văn không liên quan tới đường
  dẫn thật) — bắt buộc đọc ngữ cảnh quanh mỗi match trước khi thay, không tìm-thay hàng loạt
  không kiểm tra.
- **`setup.sh` là script thực thi, lỗi ở đây ảnh hưởng trực tiếp trải nghiệm cài đặt** —
  ưu tiên đọc kỹ toàn bộ file (không chỉ 2 dòng grep thấy) trước khi sửa.
