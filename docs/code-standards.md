# Chuẩn mã nguồn — Trợ lý Nha khoa SHI

Quy ước rút ra từ mã hiện có. Giữ nhất quán khi thêm/sửa.

## Ngôn ngữ & định dạng

- **Python 3**, `snake_case` cho hàm/biến, `UPPER_SNAKE` cho hằng module-level
  (`DEPARTMENTS`, `DOCTORS`, `SESSIONS`, `DEFAULT_VERSION`).
- **JS (mobile)**: `camelCase`, file `mobile/src/*.js` theo kebab/camel hiện có.
- Comment & chuỗi giao tiếp người dùng viết **tiếng Việt** (đúng bối cảnh dự án).
- Docstring module đầu file mô tả vai trò (xem `app/triage.py`, `app/storage.py`).

## Kiến trúc & ranh giới

- **Một khối một việc:** triage / booking / safety / push / storage độc lập, không gọi chéo
  ngoài dependency đã khai báo (xem bảng phụ thuộc trong [codebase-summary.md](codebase-summary.md)).
- **Tách logic khỏi lưu trữ:** nghiệp vụ gọi `app/storage.py`, không truy cập trực tiếp file/DB.
- **Danh mục qua `app/data.py`**, không hardcode danh sách dịch vụ/nha sĩ ở nơi khác.
- `app/chatbot.py` là nơi duy nhất giữ state machine; các khối khác thuần hàm, dễ test riêng.

## Nguyên tắc an toàn & đồng thời (bắt buộc)

- **Guardrail fail-safe:** mất DB / pattern rỗng → dùng seed baseline trong `app/safety.py`.
  Không được để guardrail biến mất vì lỗi cấu hình.
- **Ẩn PII trước khi ghi** audit log. Không log số điện thoại/tên thô. Audit log được
  bảo vệ bằng `_AUDIT_LOCK` + tự động xoay vòng tại 5MB (giữ 1 backup generation).
- **Không thêm luồng chẩn đoán/kê đơn**; giữ ưu tiên EMERGENCY/HANDOFF cao nhất mọi state.
- **Concurrency:** `app/chatbot.py` giữ `threading.Lock` per session (`session["_lock"]`),
  serialize các request cho cùng user. `app/storage.py` dùng process-wide `_JSON_LOCK` cho tất cả
  read-modify-write JSON (atomic writes via temp file + rename, chặn race condition slot booking).
  Khi lỗi concurrency: Postgres ném `psycopg.errors.UniqueViolation`, JSON mode ném
  `app.storage.SlotTakenError` hoặc `app.storage.DuplicateCodeError` — `app/booking.py` bắt cả 2.

## Cấu hình & bí mật

- Đọc cấu hình qua env (`DATABASE_URL`, `SECRET_KEY`, `ADMIN_KEY`, `PORT`) — dùng `.env`
  (`python-dotenv`). **Không commit** `.env` (đã có trong `.gitignore`).
- Fallback hợp lý khi thiếu env (JSON thay Postgres, demo key thay `SECRET_KEY`) nhưng ghi log
  rõ chế độ đang chạy (xem `[storage] Chế độ lưu trữ: ...`).

## Chất lượng AI (triage)

- Từ khóa triage là "hàm lượng AI". Sửa keywords (code hoặc DB) → **chạy lại**
  `eval/evaluate.py` để chắc Accuracy/Macro-F1 không tụt trước khi commit.
- Giữ 2 phiên bản v1/v2 để so sánh; `DEFAULT_VERSION` là bản dùng thật.

## Quy ước file mới

- File Python mới: `snake_case.py`, đặt ở gốc nếu là khối nghiệp vụ, `scripts/` nếu là tiện ích.
- Không tạo file Markdown ngoài `docs/` và `plans/` trừ khi được yêu cầu rõ.

## Test

- Dùng `pytest` (xem `requirements.txt`). Test file nằm trong `tests/` cùng cấp với `app/`.
- Chạy tất cả test: `./.venv/bin/python -m pytest tests/ -v` (hoặc `pytest tests/ -v` nếu venv đã active).
- Mỗi khối có thể test độc lập: `pytest tests/test_safety.py`, `pytest tests/test_booking.py`, v.v.
- Chạy test lại **trước khi commit** khi sửa code liên quan.

## Commit

- Conventional commits, không tham chiếu AI. Không commit secrets/`.env`/dữ liệu cá nhân.
