---
phase: 1
title: "C1 Emergency Detection Accents"
status: pending
priority: P1
dependencies: []
---

# Phase 1: C1 — Cấp cứu/chẩn đoán không bắt được câu không dấu

## Overview

`safety.check_emergency()` / `is_diagnosis_request()` / `needs_human_handoff()` so khớp
pattern **có dấu** trên `text.lower()` thô, trong khi `triage.py` (v2, dùng cho phân loại
khoa) đã chuẩn hoá bỏ dấu qua `_normalize`/`_strip_accents`/`_contains_word`. Người dùng gõ
không dấu ("kho tho nang", "dot quy", "co giat") → không kích hoạt cảnh báo 115. Rủi ro
tính mạng thật, không phải lý thuyết.

## Requirements

- Functional: `check_emergency`, `is_diagnosis_request`, `needs_human_handoff` phải bắt
  được cả câu có dấu và không dấu, dùng đúng cơ chế chuẩn hoá đã có trong `triage.py`
  (không tự chế thuật toán mới — DRY).
- Non-functional: Không đổi chữ ký hàm (`text: str -> bool`), không đổi
  `EMERGENCY_PATTERNS`/`DIAGNOSIS_REQUEST_PATTERNS`/`HANDOFF_PATTERNS` (đến từ DB/seed,
  giữ nguyên nguồn dữ liệu).

## Architecture

`triage.py` đã export `_normalize`, `_strip_accents`, `_contains_word` (dùng nội bộ,
prefix `_` nhưng cùng codebase, import trực tiếp được — không cần public API mới).
`safety.py` import các hàm này từ `triage`, chuẩn hoá cả `text` người dùng và từng
pattern trước khi so khớp, y hệt cách `triage.classify_symptoms` làm với `norm_na`.

Không thêm pattern rút gọn mới ("khó thở", "sưng mặt", "chảy máu nhiều") trong phase này —
đó là mở rộng dữ liệu (seed/DB), ngoài phạm vi "sửa bug chuẩn hoá". Nếu cần, làm ở
plan/patch riêng cho `data.py`/seed `safety_patterns`. Phase này chỉ sửa CƠ CHẾ so khớp.

## Related Code Files

- Modify: `safety.py` (hàm `check_emergency`, `is_diagnosis_request`, `needs_human_handoff`)
- Create: `tests/test_safety.py`

## Implementation Steps (TDD)

1. **Red** — viết `tests/test_safety.py`:
   - `test_check_emergency_no_accents()`: input không dấu tương ứng 1 pattern có dấu
     trong `EMERGENCY_PATTERNS` hiện tại (đọc thực tế từ `safety.EMERGENCY_PATTERNS` seed,
     không hardcode nếu pattern có thể khác) → assert `True`.
   - `test_check_emergency_with_accents_still_works()`: input có dấu y hệt pattern gốc →
     assert `True` (không regress).
   - `test_is_diagnosis_request_no_accents()`, `test_needs_human_handoff_no_accents()`:
     tương tự cho 2 hàm còn lại.
   - `test_check_emergency_pattern_with_uppercase(monkeypatch)`: monkeypatch
     `safety.EMERGENCY_PATTERNS` để chèn 1 pattern viết hoa/có khoảng trắng thừa kiểu
     dashboard-input (vd `" Khó Thở "`), gọi `check_emergency` với input không dấu tương
     ứng (`"kho tho"`) → assert `True`. Mô phỏng đúng path dữ liệu từ Supabase, không phải
     seed hardcode.
   - Chạy `pytest tests/test_safety.py -v` → xác nhận fail đúng chỗ (test không-dấu fail,
     test có-dấu pass).
2. **Green** — sửa `safety.py`:
   ```python
   from triage import _normalize, _strip_accents, _contains_word

   def check_emergency(text: str) -> bool:
       norm_na = _strip_accents(_normalize(text))
       return any(_contains_word(norm_na, _strip_accents(_normalize(p)))
                  for p in EMERGENCY_PATTERNS)
   ```
   Áp dụng cùng pattern cho `is_diagnosis_request` và `needs_human_handoff`.

   **[Red team — Accept, Finding "C1 pattern not normalized"]** Bắt buộc `_normalize(p)`
   TRƯỚC `_strip_accents(p)` cho CẢ pattern, không chỉ strip-accent. Lý do: pattern hardcode
   trong seed đã lowercase sẵn nên trước đây "có vẻ" ổn nếu chỉ strip-accent, nhưng
   `EMERGENCY_PATTERNS`/`DIAGNOSIS_REQUEST_PATTERNS`/`HANDOFF_PATTERNS` còn được nạp từ
   bảng `safety_patterns` trên Supabase (`storage.list_safety_patterns()`,
   `storage.py:301-313`) — dữ liệu admin nhập qua dashboard, không đảm bảo lowercase/không
   khoảng trắng thừa. Nếu chỉ strip-accent mà không `_normalize`, pattern admin nhập có hoa
   thường tuỳ ý sẽ không khớp `norm_na` (luôn lowercase) → cảnh báo cấp cứu cho pattern đó
   im lặng không hoạt động, đúng nguồn dữ liệu dễ nhập sai nhất. Thêm test riêng cho case
   này ở bước Red.
3. Chạy lại `pytest tests/test_safety.py -v` → pass.
4. Chạy toàn bộ `pytest tests/ -v` (test các phase khác nếu đã tồn tại) → không regress.

## Success Criteria

- [ ] `tests/test_safety.py` pass, có ca không dấu + có dấu cho cả 3 hàm.
- [ ] Không đổi chữ ký public API của `safety.py`.
- [ ] `python -c "import safety"` không lỗi import vòng (safety → triage, triage không
  import ngược safety — xác nhận trước khi sửa).

## Risk Assessment

- **Import vòng**: `triage.py` hiện không import `safety.py` (đã xác nhận qua đọc code) —
  an toàn để `safety` import `triage`. Nếu sau này ai thêm `import safety` vào `triage.py`,
  sẽ vỡ — không phải rủi ro của phase này.
- **False positive tăng**: chuẩn hoá bỏ dấu làm khớp lỏng hơn (vd "dot" có thể khớp nhầm
  từ khác nếu `_contains_word` không chặt theo từ). Giảm thiểu: dùng đúng `_contains_word`
  (khớp theo ranh giới từ) thay vì `in` thô — đã là hành vi của `triage.py`, kế thừa đúng.
