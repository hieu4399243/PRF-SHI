"""
Script seed — tạo các user mặc định (admin, doctor) vào DB.

Chạy:
    python -m scripts.seed_users
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import auth, storage


# Danh sách bác sĩ theo chuyên khoa
_SEED_DOCTORS = {
    "kham_tong_quat": [
        {"id": "bs_tq_01", "name": "BS. Nguyễn Văn An"},
        {"id": "bs_tq_02", "name": "BS. Trần Thị Bình"},
    ],
    "sau_rang": [
        {"id": "bs_sr_01", "name": "BS. Lê Minh Châu"},
    ],
    "noi_nha": [
        {"id": "bs_nn_01", "name": "BS. Phạm Quốc Dũng"},
    ],
    "nha_chu": [
        {"id": "bs_nc_01", "name": "BS. Hoàng Thị Em"},
    ],
    "nho_rang": [
        {"id": "bs_nhr_01", "name": "BS. Vũ Đình Phúc"},
    ],
    "chinh_nha": [
        {"id": "bs_cn_01", "name": "BS. Đỗ Thị Giang"},
        {"id": "bs_cn_02", "name": "BS. Ngô Văn Hải"},
    ],
    "phuc_hinh": [
        {"id": "bs_ph_01", "name": "BS. Bùi Thị Inh"},
    ],
    "tham_my": [
        {"id": "bs_tm_01", "name": "BS. Dương Văn Khang"},
    ],
    "nha_nhi": [
        {"id": "bs_nhi_01", "name": "BS. Lý Thị Lan"},
    ],
}


def seed_users():
    """Tạo các user mặc định nếu chưa tồn tại."""
    if not storage.USE_DB:
        print("⚠️  Không có DATABASE_URL — JSON mode không support seeding users.")
        print("    Hãy đặt DATABASE_URL để sử dụng feature này.")
        return

    # Tạo danh sách user từ bác sĩ
    users_to_create = [
        {
            "username": "admin",
            "password": "test123",
            "role": "admin",
            "email": "admin@shi.local",
        }
    ]

    # Thêm tất cả các bác sĩ
    for specialty, doctors in _SEED_DOCTORS.items():
        for doctor in doctors:
            users_to_create.append({
                "username": doctor["id"],
                "password": "test123",
                "role": "doctor",
                "email": f"{doctor['id']}@shi.local",
                "doctor_id": doctor["id"],
            })

    print("🌱 Seeding users...")
    created_count = 0
    for user_data in users_to_create:
        username = user_data["username"]
        # Kiểm tra user đã tồn tại chưa
        existing = storage.get_user_by_username(username)
        if existing:
            print(f"  ⏭️  {username} đã tồn tại — bỏ qua")
            continue

        try:
            auth.create_user_account(
                username=user_data["username"],
                password=user_data["password"],
                role=user_data["role"],
                email=user_data.get("email"),
                doctor_id=user_data.get("doctor_id"),
            )
            created_count += 1
            role_display = user_data['role']
            print(f"  ✅ Tạo {username} ({role_display}) thành công")
        except auth.UserAlreadyExistsError:
            print(f"  ⏭️  {username} đã tồn tại — bỏ qua")
        except Exception as e:
            print(f"  ❌ Lỗi tạo {username}: {e}")

    print(f"\n✨ Hoàn tất! Tạo mới {created_count} user.")
    print("\nThông tin login (mật khẩu của tất cả đều là: test123):")
    print("  - admin (admin)")
    print("  - guest (guest)")
    print("\nBác sĩ (username = doctor_id):")
    for specialty, doctors in _SEED_DOCTORS.items():
        print(f"  {specialty}:")
        for doctor in doctors:
            print(f"    - {doctor['id']} ({doctor['name']})")


if __name__ == "__main__":
    seed_users()
