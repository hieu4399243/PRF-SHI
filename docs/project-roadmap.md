# Lộ trình dự án — Trợ lý Nha khoa SHI

## Đã hoàn thành (demo)

- Triage rule-based (v1 có dấu / v2 không dấu), fallback than phiền chung, Q&A dịch vụ.
- Đặt lịch hội thoại + hủy lịch, chống trùng giờ/SĐT đối chiếu DB.
- Guardrails an toàn: cấp cứu→115, chặn chẩn đoán, ẩn PII, audit log, human handoff.
- Nhắc lịch (worker nền) + file `.ics` + link Google Calendar.
- Push qua Expo Push Service; fallback `app/outbox/`.
- Lưu trữ 2 chế độ (Supabase ↔ JSON) qua `app/storage.py` + script migrate.
- Trang admin (`/admin`, `ADMIN_KEY`) xem/hủy lịch.
- Hệ thống đánh giá AI (`eval/`, Accuracy/Macro-F1, v1 vs v2) + báo cáo.
- App native Expo + web demo.

## Cần vá trước production (ưu tiên cao)

| # | Việc | File | Ghi chú |
|---|------|------|---------|
| 1 | Tắt `debug=True`, chạy `gunicorn` | `app/app.py` | Dev server không dùng cho production. |
| 2 | Session bền vững (Redis/DB) | `app/chatbot.py` | `SESSIONS` in-memory → hỏng khi nhiều worker/restart. |
| 3 | Cấu hình CORS | `app/app.py` | Khi web client khác origin. |
| 4 | `API_BASE` → URL HTTPS | `mobile/src/config.js` | Bỏ IP LAN khi deploy. |
| 5 | Bật Row Level Security Supabase | (DB) | Dữ liệu sức khỏe khi mở public. |

## Nâng cấp chức năng (trung hạn)

- **LLM thật:** hiện thực `triage.classify_with_llm()` cắm Claude để NLU tiếng Việt mạnh hơn
  (đặc biệt câu mơ hồ/nhiều triệu chứng — xem `eval/dataset_complex.jsonl`).
- **Đồng bộ 2 chiều Google Calendar** (OAuth) để chặn trùng lịch phía bác sĩ.
- Mở rộng dataset đánh giá + tránh overfit từ khóa trên tập dev.
- Đa phòng khám / phân quyền admin chi tiết.

## Phát hành

- **EAS build APK Android** để nhiều người cài thử (đường tối thiểu).
- Lên Google Play (25 USD một lần) / App Store (99 USD/năm, review y tế khắt khe) — cần
  disclaimer y khoa + privacy policy. Chi tiết: [deployment-guide.md](deployment-guide.md).

## Rủi ro & phụ thuộc

- Chất lượng triage phụ thuộc từ khóa thủ công → cần theo dõi qua `eval/` mỗi lần sửa.
- Số liệu đánh giá "lạc quan" do hiệu chỉnh trên chính tập dev (nêu rõ trong
  [BAOCAO_DANHGIA.md](../BAOCAO_DANHGIA.md)).
- App y tế: ràng buộc pháp lý (NĐ 13/2023) và review store nghiêm ngặt.
