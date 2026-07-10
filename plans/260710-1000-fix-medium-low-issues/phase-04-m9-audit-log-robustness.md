---
phase: 4
title: "M9 Audit Log Robustness"
status: pending
priority: P3
dependencies: []
---

# Phase 4: M9 — Audit log không xoay vòng, timestamp không UTC, chỉ bắt OSError

## Overview

`safety.audit()` có 3 vấn đề:
1. **Không xoay vòng**: `audit_log.jsonl` ghi nối (`"a"`) vô hạn, không giới hạn kích
   thước — file lớn dần theo thời gian, không dọn dẹp.
2. **Timestamp không UTC**: `datetime.now()` dùng giờ local host — không nhất quán múi giờ
   nếu host chạy ở timezone khác nhau qua các lần deploy/di chuyển (log khó đối chiếu chéo).
3. **Chỉ bắt `OSError`**: nếu `meta` chứa giá trị không serialize được bằng `json.dumps`
   (vd object tuỳ ý lọt vào do lỗi lập trình ở nơi gọi `audit()`), `TypeError`/`ValueError`
   không được bắt → crash NGUYÊN LƯỢT CHAT của người dùng, vi phạm chính nguyên tắc đã ghi
   trong comment hiện có ("log lỗi không được làm gián đoạn hội thoại").

## Requirements

- Functional:
  - Kích thước `audit_log.jsonl` vượt ngưỡng → xoay vòng (đổi tên file hiện tại thành
    `.1`, ghi đè `.1` cũ nếu có, bắt đầu file mới rỗng) TRƯỚC khi ghi dòng tiếp theo.
  - Timestamp mỗi dòng log là UTC (`datetime.now(timezone.utc)`), không phụ thuộc giờ hệ
    thống host.
  - Lỗi serialize `meta`/`message` (bất kỳ exception nào từ `json.dumps`/`open`/`write`)
    KHÔNG được làm crash lượt chat — bắt rộng hơn `OSError`.
- Non-functional: Không đổi chữ ký `audit(session_id, role, message, meta=None)`. Không đổi
  format 1 dòng log hợp lệ (vẫn JSON 1 dòng, các field `ts`/`session`/`role`/`message`/`meta`
  giữ nguyên tên, chỉ đổi GIÁ TRỊ của `ts` sang UTC).

## Architecture

```python
import threading
from datetime import datetime, timezone

AUDIT_LOG_MAX_BYTES = 5 * 1024 * 1024  # 5MB, 1 thế hệ xoay vòng (đủ cho demo/đồ án)

_AUDIT_LOCK = threading.Lock()


def _rotate_audit_log_if_needed():
    """Phải gọi trong lúc giữ _AUDIT_LOCK (xem audit())."""
    try:
        if (os.path.exists(AUDIT_LOG_PATH)
                and os.path.getsize(AUDIT_LOG_PATH) >= AUDIT_LOG_MAX_BYTES):
            rotated_path = AUDIT_LOG_PATH + ".1"
            os.replace(AUDIT_LOG_PATH, rotated_path)  # ghi đè .1 cũ nếu có
    except OSError:
        pass  # rotation lỗi không được chặn ghi log mới


def audit(session_id: str, role: str, message: str, meta: dict | None = None):
    """Ghi một dòng log JSON cho mỗi lượt hội thoại (UTC, tự xoay vòng, fail-safe)."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session": session_id,
        "role": role,
        "message": mask_pii(message),
        "meta": meta or {},
    }
    try:
        with _AUDIT_LOCK:
            _rotate_audit_log_if_needed()
            with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # log lỗi (bất kỳ loại nào, kể cả TypeError từ json.dumps trên meta
              # không serialize được) không được làm gián đoạn hội thoại.
```
Đổi `except OSError:` (dòng cuối cũ) thành `except Exception:` — mở rộng phạm vi bắt lỗi
đúng như comment hiện có đã tuyên bố nhưng code cũ chưa thực hiện đủ.

**[Red team — Accept, Finding "rotation là race check-then-act không khoá"]** `audit()`
được gọi từ NHIỀU session đồng thời (khác với khoá per-session mới thêm ở Phase 1 — khoá đó
chỉ serialize CÙNG 1 session, không serialize giữa CÁC session khác nhau). Nếu 2 session
khác nhau cùng gọi `audit()` đúng lúc file chạm ngưỡng xoay vòng mà không có khoá riêng cho
audit log, cả 2 có thể cùng thấy "cần rotate", cùng `os.replace`, hoặc 1 thread ghi dòng mới
vào file VỪA bị đổi tên thành `.1` (mất dòng đó khỏi file chính). Thêm `_AUDIT_LOCK` (giống
hệt cách `_JSON_LOCK` bảo vệ storage.py ở Phase 2 — nhất quán pattern, KHÔNG dùng lại cùng
1 lock giữa 2 module khác nhau, mỗi module có lock riêng của mình) bọc quanh TOÀN BỘ
`_rotate_audit_log_if_needed()` + mở file + ghi, đảm bảo rotate-và-ghi atomic đối với các
lời gọi `audit()` đồng thời từ session khác nhau.

## Related Code Files

- Modify: `safety.py` (`audit`, thêm `_rotate_audit_log_if_needed`, `AUDIT_LOG_MAX_BYTES`)
- Modify: `tests/test_safety.py` (file đã có từ vòng Critical — đọc trước, thêm test mới,
  không phá test cũ)

## Implementation Steps (TDD)

1. **Đọc trước**: `tests/test_safety.py` hiện tại để biết cách các test khác đã setup/dọn
   `AUDIT_LOG_PATH` (nếu có), tránh xung đột fixture.
2. **Red** — thêm vào `tests/test_safety.py`:
   - `test_audit_uses_utc_timestamp(monkeypatch, tmp_path)`: monkeypatch
     `safety.AUDIT_LOG_PATH` sang file tạm, gọi `safety.audit(...)`, đọc dòng log, parse
     `ts` → assert timezone offset là `+00:00` (UTC), KHÔNG phải giờ local.
   - `test_audit_rotates_when_oversized(monkeypatch, tmp_path)`: monkeypatch
     `safety.AUDIT_LOG_PATH` sang file tạm, monkeypatch `safety.AUDIT_LOG_MAX_BYTES` xuống
     rất nhỏ (vd `10` bytes) để test nhanh, ghi trước 1 dòng log giả lớn hơn ngưỡng vào file
     tạm, gọi `safety.audit(...)` lần nữa → assert tồn tại file `<path>.1` chứa nội dung
     dòng CŨ, file chính chỉ chứa dòng MỚI.
   - `test_audit_does_not_crash_on_unserializable_meta(monkeypatch, tmp_path)`: monkeypatch
     `AUDIT_LOG_PATH`, gọi `safety.audit(sid, "user", "msg", {"bad": object()})` (object()
     không serialize được bằng `json.dumps`) → assert KHÔNG raise exception (trước fix,
     phải raise `TypeError` vì chỉ bắt `OSError` — đúng Red state).
   - `test_audit_concurrent_writes_no_lost_lines(monkeypatch, tmp_path)`: **[Red team —
     Accept]** monkeypatch `AUDIT_LOG_PATH` sang file tạm, N thread (vd 20) gọi
     `safety.audit(sid, "user", f"msg-{i}", {})` đồng thời → sau khi tất cả hoàn tất, đếm số
     dòng trong file log (cộng cả file `.1` nếu có do rotation ngẫu nhiên trùng lúc) → assert
     tổng số dòng == N (không mất dòng nào do race ghi/rotate).
   - Chạy `pytest tests/test_safety.py -v` → xác nhận 4 test mới fail đúng chỗ, test cũ (từ
     C1) vẫn pass.
3. **Green** — sửa `safety.py` theo Architecture.
4. Chạy lại → toàn bộ pass (cả 8 test cũ từ C1 lẫn 4 test mới).

## Success Criteria

- [ ] `tests/test_safety.py` pass toàn bộ (12 test: 8 cũ + 4 mới).
- [ ] Timestamp log là UTC.
- [ ] File log xoay vòng đúng khi vượt ngưỡng kích thước.
- [ ] Lỗi serialize `meta` không làm crash lượt chat (bắt `Exception` rộng, không chỉ
  `OSError`).
- [ ] Ghi log đồng thời từ nhiều session không mất dòng (bọc `_AUDIT_LOCK`).

## Risk Assessment

- **Xoay vòng chỉ 1 thế hệ (`.1`)** — không phải logrotate đầy đủ nhiều thế hệ. Đủ cho quy
  mô đồ án (tránh file phình vô hạn), không xây hệ thống rotation phức tạp hơn (YAGNI).
- **`_rotate_audit_log_if_needed` tự bắt `OSError` riêng** — nếu rotation lỗi (vd quyền ghi),
  KHÔNG được chặn việc ghi log mới tiếp tục thử (file sẽ tiếp tục phình to hơn ngưỡng cho
  tới khi rotation thành công lần sau) — chấp nhận, ưu tiên "log vẫn ghi được" hơn "log luôn
  đúng kích thước".
- **Đổi `except OSError` → `except Exception`** là thay đổi rộng hơn — cân nhắc: có thể che
  giấu lỗi lập trình thật (vd `AUDIT_LOG_PATH` bị None do lỗi ở nơi khác). Chấp nhận
  trade-off này vì đúng tinh thần thiết kế đã ghi rõ trong comment gốc ("log lỗi không được
  làm gián đoạn hội thoại") — ưu tiên tính liên tục của trải nghiệm người dùng hơn phát hiện
  sớm lỗi lập trình qua audit log.
