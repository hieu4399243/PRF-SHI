# Tổng quan dự án & PDR — Trợ lý Nha khoa SHI

## 1. Tóm tắt

Chatbot tiếng Việt cho **một phòng khám nha khoa**. Bệnh nhân mô tả triệu chứng răng
miệng → hệ thống **phân loại đúng nhóm dịch vụ nha khoa** (triage) → **đặt lịch hẹn** →
**nhắc lịch** qua push notification / file `.ics`. Đề tài demo học phần PRF/SHI, kèm
**hệ thống đánh giá AI** (Precision/Recall/F1, so sánh v1 vs v2) ở `eval/` và
[BAOCAO_DANHGIA.md](../BAOCAO_DANHGIA.md).

## 2. Vấn đề & mục tiêu

| Mục | Nội dung |
|-----|----------|
| **Vấn đề** | Bệnh nhân không rõ triệu chứng của mình thuộc dịch vụ nào; đặt lịch qua điện thoại thủ công, dễ trùng slot, thiếu nhắc lịch. |
| **Mục tiêu chính** | Tự động điều hướng triệu chứng → dịch vụ đúng, đặt lịch không trùng, nhắc lịch tự động. |
| **Mục tiêu AI** | Đo được chất lượng phân loại (Accuracy/Macro-F1) và cải thiện qua phiên bản. |
| **Ràng buộc an toàn** | Y tế: phát hiện cấp cứu (→115), không chẩn đoán/kê đơn, ẩn PII, audit log (NĐ 13/2023). |

## 3. Người dùng & phạm vi

- **Bệnh nhân** — app native (Expo) hoặc web demo, chat để chọn dịch vụ và đặt lịch.
- **Quản trị phòng khám** — trang `/admin` (bảo vệ bằng `ADMIN_KEY`) xem/hủy lịch.
- **Phạm vi demo:** một phòng khám, một ngôn ngữ (tiếng Việt), triage rule-based (có chỗ
  cắm LLM). Không phải hệ thống HIS/EMR đầy đủ.

## 4. Yêu cầu chức năng (đã hiện thực)

1. **Triage** — phân loại triệu chứng → 1 trong 9 nhóm dịch vụ (`triage.py`, v1 có dấu /
   v2 không dấu mặc định). Fallback than phiền chung; trả lời câu hỏi "dịch vụ X là gì".
2. **Đặt lịch hội thoại** — chọn dịch vụ → bác sĩ → ngày → giờ trống → tên → SĐT → xác nhận
   (`booking.py`), kiểm tra trùng giờ/trùng SĐT trực tiếp với DB lúc xác nhận.
3. **Hủy lịch** — tra theo SĐT, chọn lịch, xác nhận (`status='cancelled'`).
4. **An toàn (guardrails)** — cấp cứu → 115, chặn chẩn đoán/kê đơn, human handoff, ẩn PII,
   audit log (`safety.py`).
5. **Nhắc lịch** — worker nền quét lịch, bắn push trước 1 ngày / 2 giờ (`reminder_worker.py`).
6. **Thêm vào lịch** — sinh file `.ics` (có VALARM) + link Google Calendar (`calendar_ics.py`).
7. **Đánh giá AI** — `eval/evaluate.py` tính Accuracy/Macro-F1 cho v1 & v2.

## 5. Yêu cầu phi chức năng

| Thuộc tính | Cách đáp ứng hiện tại |
|-----------|----------------------|
| **Offline-first / dễ demo** | Không cần DB/LLM vẫn chạy: fallback file JSON + rule-based. |
| **Lưu trữ bền vững** | Có `DATABASE_URL` → Postgres/Supabase; không thì file JSON (`storage.py`). |
| **An toàn tính mạng** | Guardrail fail-safe: pattern rỗng/mất DB → dùng seed trong `safety.py`. |
| **Bảo mật cấu hình** | `SECRET_KEY`, `ADMIN_KEY`, `DATABASE_URL` qua `.env` (không commit). |
| **Quyền riêng tư** | Ẩn PII trước khi ghi audit log (NĐ 13/2023). |

## 6. Kết quả đánh giá AI (mới nhất)

Tập dev 63 câu: **v2 — Accuracy 100%, Macro-F1 1.0**; v1 — 77.8% / 0.87. Lưu ý: từ khóa
được hiệu chỉnh trên chính tập này nên là số "lạc quan"; phân tích trung thực ở
[BAOCAO_DANHGIA.md](../BAOCAO_DANHGIA.md).

## 7. Ngoài phạm vi (demo)

- Tích hợp LLM thật (`triage.classify_with_llm()` là placeholder cắm Claude).
- Đồng bộ 2 chiều Google Calendar qua OAuth.
- Đa phòng khám, đa ngôn ngữ, session bền vững (hiện in-memory).

## Tài liệu liên quan

- Kiến trúc: [system-architecture.md](system-architecture.md)
- Bản đồ mã & chuẩn: [codebase-summary.md](codebase-summary.md) · [code-standards.md](code-standards.md)
- Lộ trình: [project-roadmap.md](project-roadmap.md)
- Triển khai: [deployment-guide.md](deployment-guide.md) · [getting-started-guide.md](getting-started-guide.md)
- Lưu trữ/DB: [database-storage-guide.md](database-storage-guide.md)
