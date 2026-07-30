# Trợ lý Nha khoa SHI

**Portal bệnh nhân** cho một phòng khám nha khoa: xem lịch sử điều trị → nhận
**gợi ý dịch vụ cá nhân hoá** kèm lý do dễ hiểu (AI) → đặt lịch → nhắc lịch qua
push/`.ics`. Chatbot triage tiếng Việt là **widget nằm trong trang**, không phải
một trang riêng — bệnh nhân mô tả triệu chứng, bot phân loại đúng nhóm dịch vụ và
dẫn đặt lịch. Đề tài demo (PRF/SHI), có **hệ thống đánh giá AI**
(Precision/Recall/F1, so sánh v1 vs v2) ở `eval/`.

Tài liệu chi tiết nằm ở [`docs/`](docs/) — README này chỉ là điểm khởi động nhanh.

## Kiến trúc (tóm tắt)

Hai phần, nối nhau qua REST JSON: **Backend** Flask (`app/`) phục vụ web demo, trang
quản trị (`/admin`) và các endpoint `/api/*`; **Mobile** React Native/Expo (`mobile/`),
mở bằng Expo Go + QR, gọi backend qua IP LAN cấu hình ở `mobile/src/config.js`
(`API_BASE`) — phải **cùng Wi-Fi**.

Chi tiết đầy đủ (sơ đồ thành phần, máy trạng thái hội thoại, luồng an toàn, API,
lớp lưu trữ): **[docs/system-architecture.md](docs/system-architecture.md)**.
Sơ đồ file & vai trò từng module: **[docs/codebase-summary.md](docs/codebase-summary.md)**.

## Cài đặt & chạy nhanh

```bash
# Backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
PORT=5001 .venv/bin/python -m app.main        # API tại http://0.0.0.0:5001

# App native
cd mobile && npm install && npx expo start -c   # quét QR bằng Expo Go
```

Hoặc dùng script gộp: `./setup.sh` (cài backend + mobile, tự dò IP LAN).

> macOS chiếm cổng 5000 (AirPlay Receiver) → backend chạy ở cổng 5001.

Hướng dẫn đầy đủ (Docker Compose, biến môi trường, production, troubleshooting):
**[docs/deployment-guide.md](docs/deployment-guide.md)**.

## Thử nhanh

Mở `http://127.0.0.1:5001` — đó là **portal bệnh nhân**. Khách chưa đăng nhập vẫn
xem được gợi ý (dịch vụ phổ biến) và vẫn đặt được lịch qua ô chat góc phải.

Đăng nhập ở `/login` để thấy gợi ý cá nhân hoá (mật khẩu tất cả: `test123`):

| User | Xem được gì |
|------|-------------|
| `bn101` | quá hạn tái khám → `followup_due` |
| `bn103` | vừa nội nha → `care_pathway` gợi ý phục hình |
| `bn104` | `similar_patients` (đồng xuất hiện) |
| `bn107` | **cold-start** — không hiện %, chỉ thời lượng + giá |
| `bn108` | trẻ em → chỉ gợi ý nha khoa trẻ em |
| `admin` / `bs_sr_01` | tự chuyển sang trang admin / nha sĩ |

Cơ chế gợi ý (6 luật, noisy-OR, bộ lọc an toàn):
**[docs/patient-recommendation-design.md](docs/patient-recommendation-design.md)**.

Thử chatbot trong widget:

- *"răng tôi bị sâu và ê buốt khi ăn ngọt"* → dịch vụ **Trám răng / Sâu răng** → đặt lịch.
- *"toi muon nieng rang"* (không dấu) → **Chỉnh nha** (nhờ engine v2 không phân biệt dấu).
- *"chảy máu chân răng và hôi miệng"* → **Nha chu**.
- *"mặt tôi sưng mặt lan và khó nuốt"* → cảnh báo **cấp cứu, gọi 115**.
- *"cho tôi gặp nhân viên"* → **chuyển người thật** (handoff).
- Gõ **"làm lại"** để bắt đầu phiên mới.

## Test & đánh giá hệ thống AI

```bash
DATABASE_URL= .venv/bin/python -m pytest   # bộ test backend (tests/)
.venv/bin/python eval/evaluate.py          # Accuracy/Precision/Recall/Macro-F1 cho v1 & v2
```

> ⚠️ **Luôn đặt `DATABASE_URL=`** khi chạy pytest. Bộ test giả định chế độ JSON;
> thiếu biến này thì test sẽ ghi thẳng vào Supabase thật.
>
> `REC_LLM_REASON=0` để tắt phần LLM viết lý do gợi ý (nhanh hơn, kết quả tái lập
> được — dùng khi đánh giá).

Chi tiết dataset, cách chấm điểm LLM: **[docs/codebase-summary.md § Evaluation System](docs/codebase-summary.md#evaluation-system-eval)**.

## Bật LLM cho triage

Mặc định dự án chạy được **không cần API key** (rule-based v2). Muốn bot hiểu câu
diễn giải tự do, thêm `OPENROUTER_API_KEY` + `LLM_MODEL` vào `.env` — xem
**[docs/system-architecture.md § Triage Engine](docs/system-architecture.md#triage-engine-three-versions)**.

Thử bằng tay — gõ câu, xem hai engine trả lời cạnh nhau:

```bash
./.venv/bin/python scripts/try_llm.py --suite     # bộ câu mẫu
./.venv/bin/python scripts/try_llm.py             # gõ câu tương tác
```

## Tài liệu chi tiết (`docs/`)

| File | Nội dung |
|------|----------|
| [project-overview-pdr.md](docs/project-overview-pdr.md) | Bài toán, yêu cầu, phạm vi, success metrics |
| [system-architecture.md](docs/system-architecture.md) | Sơ đồ kiến trúc, máy trạng thái, triage engine, an toàn, storage, API |
| [codebase-summary.md](docs/codebase-summary.md) | Vai trò từng module/file trong `app/`, `mobile/`, `eval/`, `tests/` |
| [code-standards.md](docs/code-standards.md) | Quy ước đặt tên, quy tắc phụ thuộc, pattern xử lý lỗi |
| [deployment-guide.md](docs/deployment-guide.md) | Cài đặt local/Docker/production, biến môi trường, troubleshooting |
| [project-roadmap.md](docs/project-roadmap.md) | Khoảng trống trước production, hướng nâng cấp |
| [patient-recommendation-design.md](docs/patient-recommendation-design.md) | **Đề xuất:** patient portal + gợi ý dịch vụ AI (REC-01/02, PAT-01) |


<!-- Đăng nhập thử ở /login (mật khẩu tất cả là test123):
./.venv/bin/python -m app.main
User	Xem được gì
bn101	quá hạn tái khám → followup_due
bn103	vừa nội nha → care_pathway gợi ý phục hình
bn104	similar_patients (đồng xuất hiện)
bn107	cold-start — dải cam, không hiện %, chỉ thời lượng + giá
bn108	trẻ em → chỉ gợi ý nha khoa trẻ em
admin / bs_sr_01	trang admin / nha sĩ như trước
Hai lưu ý khi test: .venv/bin/pip hỏng shebang (venv tạo từ đường dẫn cũ Desktop/PRF-SHI) → dùng .venv/bin/python -m pip. Và luôn đặt DATABASE_URL= khi chạy pytest — bộ test giả định JSON mode, chạy thiếu biến này sẽ ghi thật vào Supabase.

Muốn tắt LLM (chạy nhanh hơn, kết quả tái lập được): REC_LLM_REASON=0. -->