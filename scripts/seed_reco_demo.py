"""
Seed lịch sử điều trị GIẢ ĐỊNH để demo + đánh giá engine gợi ý (REC-01/02).

Vì sao cần: dữ liệu thật của phòng khám chỉ trải trong ~1.5 tháng, nên không có
bệnh nhân nào quá hạn tái khám 6 tháng, cũng không đủ bệnh nhân trùng nhau để
tính đồng xuất hiện. Không seed thì mọi bệnh nhân đều rơi vào nhánh cold-start và
không có gì để demo.

Mỗi hồ sơ dưới đây được dựng để kích hoạt ĐÚNG MỘT `reason_code`, nhờ vậy chạy
engine lên là thấy ngay luật nào hỏng:

    0900000101  followup_due      nha sĩ hẹn tái khám, đã quá hạn 2 tháng
    0900000102  past_treatment    tẩy trắng 14 tháng trước (chu kỳ 12) -> tới chu kỳ
    0900000103  care_pathway      nội nha 2 tháng trước -> gợi ý phục hình
    0900000104  similar_patients  3 hồ sơ có cặp (khám tổng quát + trám răng)
    0900000105  similar_patients  ...
    0900000106  similar_patients  ...
    0900000107  cold-start        1 lượt duy nhất (< 3) -> popularity + độ tuổi
    0900000108  age_group         trẻ em, 3 lượt nha khoa trẻ em

Hai điều kiện dữ liệu mà bộ hồ sơ này phải thoả, nếu không luật tương ứng im lặng:

  - Ít nhất 3 hồ sơ có >= 3 lượt điều trị, nếu không mọi bệnh nhân đều rơi vào
    nhánh cold-start (ngưỡng TC-REC-002) và `similar_patients` không bao giờ chạy.
  - `similar_patients` cần >= MIN_SUPPORT (3) bệnh nhân từng dùng cùng một dịch
    vụ, và tỉ lệ P(B|A) phải KHÁC 100% — nếu mọi hồ sơ đều dùng cùng bộ dịch vụ
    thì tỉ lệ luôn là 100% và con số trên card trở nên vô nghĩa.

`followup` chỉ được đặt cho hồ sơ 101: nó mang nghĩa "nha sĩ đã hẹn tái khám".
Đặt cho mọi dịch vụ định kỳ thì luật `followup_due` sẽ nuốt hết `past_treatment`.

Bản ghi seed KHÔNG gắn với lịch hẹn nào (`appointment_code=NULL`) nên không đụng
tới dữ liệu đặt lịch thật; `history_id` cố định nên chạy lại nhiều lần vẫn an toàn.
Tất cả SĐT đều thuộc dải 09000001xx để dễ tìm và dễ xoá.

Chạy:
    ./.venv/bin/python scripts/seed_reco_demo.py
    ./.venv/bin/python scripts/seed_reco_demo.py --purge   # xoá dữ liệu seed
"""

import argparse
import os
import sys
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.core import auth, storage  # noqa: E402
from app.core.catalog import service_meta  # noqa: E402

DEMO_PHONE_PREFIX = "090000010"
DEMO_PASSWORD = "test123"  # cùng quy ước với scripts/seed_users.py

# (phone, tên, năm sinh, [(số tháng trước, mã dịch vụ, doctor_id, hẹn tái khám sau
#  bao nhiêu tháng | None), ...])
DEMO_PATIENTS = [
    ("0900000101", "Nguyễn Văn An (demo)", 1990, [
        (8, "kham_tong_quat", "bs_tq_01", 6),   # nha sĩ hẹn 6 tháng -> quá hạn 2
        (26, "nha_chu", "bs_nc_01", None),
        (30, "tham_my", "bs_tm_01", None),
    ]),
    ("0900000102", "Trần Thị Bích (demo)", 1995, [
        (14, "tham_my", "bs_tm_01", None),      # chu kỳ 12 -> tới hạn làm lại
        (3, "kham_tong_quat", "bs_tq_01", None),  # 3 < 6 -> CHƯA tới chu kỳ
        (18, "nho_rang", "bs_nhr_01", None),
    ]),
    ("0900000103", "Lê Minh Cường (demo)", 1985, [
        (2, "noi_nha", "bs_nn_01", None),       # -> care_pathway: phục hình
        (9, "kham_tong_quat", "bs_tq_02", None),
        (15, "nha_chu", "bs_nc_01", None),
    ]),
    ("0900000104", "Phạm Thị Dung (demo)", 1992, [
        (10, "kham_tong_quat", "bs_tq_01", None),
        (9, "sau_rang", "bs_sr_01", None),
        (20, "nho_rang", "bs_nhr_01", None),
    ]),
    ("0900000105", "Hoàng Văn Em (demo)", 1988, [
        (11, "kham_tong_quat", "bs_tq_02", None),
        (10, "sau_rang", "bs_sr_01", None),
        (24, "chinh_nha", "bs_cn_01", None),
    ]),
    ("0900000106", "Vũ Thị Phượng (demo)", 1979, [
        (12, "kham_tong_quat", "bs_tq_01", None),
        (11, "sau_rang", "bs_sr_01", None),
        (30, "phuc_hinh", "bs_ph_01", None),
    ]),
    ("0900000107", "Đỗ Văn Giang (demo)", 2000, [
        (1, "kham_tong_quat", "bs_tq_01", None),   # 1 lượt -> cold-start
    ]),
    ("0900000108", "Bé Ngô Hà (demo)", 2018, [
        (7, "nha_nhi", "bs_nhi_01", 6),
        (13, "nha_nhi", "bs_nhi_01", None),
        (19, "nha_nhi", "bs_nhi_01", None),
    ]),
]


def _months_ago(months, today=None):
    """Ngày cách đây `months` tháng, dạng ISO."""
    d = today or date.today()
    month = d.month - 1 - months
    year = d.year + month // 12
    month = month % 12 + 1
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    day = min(d.day, [31, 29 if leap else 28, 31, 30, 31, 30,
                      31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day).isoformat()


def _add_months(iso_date, months):
    d = date.fromisoformat(iso_date)
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    day = min(d.day, [31, 29 if leap else 28, 31, 30, 31, 30,
                      31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day).isoformat()


def build_records(today=None):
    """Dựng danh sách bản ghi điều trị từ DEMO_PATIENTS. Hàm thuần, test được."""
    now = datetime.now().isoformat(timespec="seconds")
    records = []
    for phone, _name, _birth_year, visits in DEMO_PATIENTS:
        for i, (months, service_code, doctor_id, followup) in enumerate(visits, start=1):
            treatment_date = _months_ago(months, today)
            records.append({
                "history_id": f"th-demo-{phone}-{i}",
                "appointment_code": None,
                "patient_id": None,       # điền ở seed_accounts() nếu có DB
                "patient_phone": phone,
                "service_code": service_code,
                "doctor_id": doctor_id,
                "treatment_date": treatment_date,
                "outcome": "success",
                "followup_required": bool(followup),
                "followup_due_date": (_add_months(treatment_date, followup)
                                      if followup else None),
                "patient_rating": 5,
                "created_at": now,
            })
    return records


def seed_accounts():
    """Tạo tài khoản role='patient' cho các hồ sơ demo. Trả dict {phone: user_id}.

    Chỉ chạy được trên Postgres (bảng users không có JSON-mode fallback). Không có
    DB thì lịch sử vẫn seed được và neo theo SĐT, nhưng các luật theo ĐỘ TUỔI sẽ
    không kích hoạt vì `birth_year` nằm trên tài khoản.
    """
    ids = {}
    if not storage.USE_DB:
        print("⚠️  Không có DATABASE_URL — bỏ qua việc tạo tài khoản bệnh nhân.")
        print("    Lịch sử vẫn seed (neo theo SĐT), nhưng luật theo độ tuổi sẽ không chạy.")
        return ids

    for phone, name, birth_year, _visits in DEMO_PATIENTS:
        username = f"bn{phone[-3:]}"
        existing = storage.get_user_by_username(username)
        if existing:
            ids[phone] = existing.get("patient_id")
            print(f"  ⏭️  {username} đã tồn tại — bỏ qua")
            continue
        try:
            # Hồ sơ bệnh nhân (bảng `patients`) là thực thể chính; tài khoản đăng
            # nhập chỉ trỏ tới nó qua `users.patient_id`.
            profile = next((p for p in storage.list_patients()
                            if (p.get("phone") or "").strip() == phone), None)
            if not profile:
                profile = storage.create_patient_profile(name=name, phone=phone,
                                                         email=f"{username}@shi.local")
            storage.set_patient_clinical(profile["id"], birth_year=birth_year)

            user = auth.create_user_account(
                username=username,
                password=DEMO_PASSWORD,
                role="patient",
                email=f"{username}@shi.local",
                phone=phone,
                patient_id=profile["id"],
            )
            ids[phone] = profile["id"]
            print(f"  ✅ Tạo {username} (patient, {name})")
        except Exception as exc:  # noqa: BLE001
            print(f"  ❌ Lỗi tạo {username}: {exc}")
    return ids


def purge():
    """Xoá dữ liệu seed demo (chỉ các bản ghi có history_id bắt đầu 'th-demo-')."""
    if storage.USE_DB:
        storage.init_schema()
        with storage._connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM treatment_history "
                        "WHERE history_id LIKE 'th-demo-%%'")
            n_th = cur.rowcount
            cur.execute("DELETE FROM users WHERE role = 'patient' AND phone LIKE %s",
                        (DEMO_PHONE_PREFIX + "%",))
            n_u = cur.rowcount
            conn.commit()
        print(f"🧹 Đã xoá {n_th} bản ghi điều trị demo, {n_u} tài khoản demo.")
        return

    items = storage._json_load(storage.TREATMENT_HISTORY_PATH, [])
    keep = [r for r in items
            if not str(r.get("history_id", "")).startswith("th-demo-")]
    storage._json_save(storage.TREATMENT_HISTORY_PATH, keep)
    print(f"🧹 Đã xoá {len(items) - len(keep)} bản ghi điều trị demo.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--purge", action="store_true", help="xoá dữ liệu seed demo")
    parser.add_argument("--no-accounts", action="store_true",
                        help="chỉ seed lịch sử, không tạo tài khoản bệnh nhân")
    args = parser.parse_args()

    print(f"[seed-reco] Chế độ lưu trữ: "
          f"{'Postgres/Supabase' if storage.USE_DB else 'file JSON (local)'}")

    if args.purge:
        purge()
        return

    print("🌱 Tạo tài khoản bệnh nhân demo...")
    ids = {} if args.no_accounts else seed_accounts()

    records = build_records()
    for r in records:
        r["patient_id"] = ids.get(r["patient_phone"])

    added = sum(1 for r in records if storage.add_treatment(r))
    print(f"\n✨ Lịch sử điều trị: thêm mới {added}/{len(records)} bản ghi "
          f"({len(records) - added} đã có).")
    print(f"   {len(DEMO_PATIENTS)} hồ sơ bệnh nhân demo, SĐT {DEMO_PHONE_PREFIX}x")
    if ids:
        print(f"   Login demo: username bn101..bn108, mật khẩu {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
