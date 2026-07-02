"""
Chuyển dữ liệu từ file JSON (appointments.json, device_tokens.json) lên Postgres
(Supabase). Bảng được tạo tự động nếu chưa có.

Cách dùng:
    1) Tạo project trên Supabase, lấy Connection string (Transaction pooler).
    2) Đặt biến môi trường (hoặc ghi vào file .env ở thư mục gốc):
           DATABASE_URL=postgresql://...:...@...pooler.supabase.com:6543/postgres
    3) Chạy:
           ./.venv/bin/python scripts/migrate_to_supabase.py

Script an toàn khi chạy lại (idempotent): trùng mã lịch hẹn / trùng token sẽ bỏ qua.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import storage  # noqa: E402

APPTS = os.path.join(ROOT, "appointments.json")
TOKENS = os.path.join(ROOT, "device_tokens.json")


def main():
    if not storage.USE_DB:
        print("❌ Chưa thấy DATABASE_URL. Hãy đặt biến môi trường rồi chạy lại.")
        sys.exit(1)

    storage.init_schema()
    print("✅ Đã tạo/đảm bảo bảng trên Postgres.")

    # Danh mục dịch vụ + nha sĩ (seed từ dict tĩnh trong data.py)
    import data
    n_sv, n_dr = storage.seed_catalog(data._SEED_DEPARTMENTS, data._SEED_DOCTORS)
    print(f"✅ Đã nạp danh mục: {n_sv} dịch vụ, {n_dr} nha sĩ (bỏ qua phần đã có).")

    # Bộ pattern an toàn (guardrail): cấp cứu / chặn chẩn đoán / human handoff
    import safety
    n_sp = storage.seed_safety_patterns({
        "emergency": safety._SEED_EMERGENCY_PATTERNS,
        "diagnosis": safety._SEED_DIAGNOSIS_REQUEST_PATTERNS,
        "handoff": safety._SEED_HANDOFF_PATTERNS,
    })
    print(f"✅ Đã nạp {n_sp} pattern an toàn (bỏ qua phần đã có).")

    # Lịch hẹn
    appts = json.load(open(APPTS, encoding="utf-8")) if os.path.exists(APPTS) else []
    existing = {a["code"] for a in storage.list_appointments()}
    n_appt = 0
    for a in appts:
        if a.get("code") in existing:
            continue
        storage.add_appointment(a)
        n_appt += 1
    print(f"✅ Đã nạp {n_appt} lịch hẹn (bỏ qua {len(appts) - n_appt} đã có).")

    # Device tokens
    tokens = json.load(open(TOKENS, encoding="utf-8")) if os.path.exists(TOKENS) else {}
    n_tok = 0
    for session_id, toks in tokens.items():
        for t in toks:
            storage.add_token(session_id, t)
            n_tok += 1
    print(f"✅ Đã nạp {n_tok} device token.")
    print("\nHoàn tất. Mở Supabase → Table editor để xem/quản lý dữ liệu online.")


if __name__ == "__main__":
    main()
