"""
Dữ liệu tĩnh cho phòng khám SHI: danh sách khoa, bác sĩ và khung giờ trống.
Trong sản phẩm thật, phần này sẽ được thay bằng cơ sở dữ liệu (DB) thực tế.
"""

from datetime import date, timedelta

# ---------------------------------------------------------------------------
# DANH MỤC KHOA  (mỗi khoa có mã, tên, mô tả và bộ từ khóa triệu chứng)
# Bộ từ khóa được dùng cho "triage engine" (xem triage.py) để phân loại
# triệu chứng tiếng Việt -> đúng khoa.
# ---------------------------------------------------------------------------
DEPARTMENTS = {
    "tim_mach": {
        "name": "Tim mạch",
        "desc": "Bệnh lý tim, huyết áp, mạch máu.",
        "keywords": [
            "tim", "đau ngực", "hồi hộp", "đánh trống ngực", "huyết áp",
            "cao huyết áp", "tăng huyết áp", "khó thở khi gắng sức", "loạn nhịp",
            "nhịp tim", "mệt khi leo cầu thang",
        ],
    },
    "ho_hap": {
        "name": "Hô hấp",
        "desc": "Bệnh lý phổi, đường thở.",
        "keywords": [
            "ho", "ho khan", "ho có đờm", "khó thở", "hụt hơi", "đau họng",
            "viêm họng", "khò khè", "hen", "hen suyễn", "tức ngực khi ho",
            "đờm", "cảm cúm", "sổ mũi", "nghẹt mũi",
        ],
    },
    "tieu_hoa": {
        "name": "Tiêu hóa",
        "desc": "Dạ dày, ruột, gan mật.",
        "keywords": [
            "đau bụng", "đau dạ dày", "ợ chua", "ợ hơi", "buồn nôn", "nôn",
            "tiêu chảy", "táo bón", "khó tiêu", "đầy hơi", "chướng bụng",
            "đi ngoài", "phân lỏng", "trào ngược", "ăn không tiêu",
        ],
    },
    "than_kinh": {
        "name": "Thần kinh",
        "desc": "Đau đầu, chóng mặt, thần kinh.",
        "keywords": [
            "đau đầu", "nhức đầu", "chóng mặt", "hoa mắt", "mất ngủ", "tê tay",
            "tê chân", "co giật", "động kinh", "mất trí nhớ", "đau nửa đầu",
            "migraine", "run tay",
        ],
    },
    "co_xuong_khop": {
        "name": "Cơ xương khớp",
        "desc": "Xương, khớp, cơ, cột sống.",
        "keywords": [
            "đau lưng", "đau khớp", "đau gối", "đau vai", "đau cổ", "thoái hóa",
            "thoát vị", "đau xương", "cứng khớp", "sưng khớp", "đau cơ",
            "bong gân", "đau cột sống", "tê mỏi",
        ],
    },
    "da_lieu": {
        "name": "Da liễu",
        "desc": "Da, tóc, móng, dị ứng da.",
        "keywords": [
            "ngứa", "nổi mẩn", "phát ban", "mụn", "mề đay", "viêm da", "nấm da",
            "rụng tóc", "vảy nến", "dị ứng da", "nổi mề đay", "da khô", "chàm",
        ],
    },
    "tai_mui_hong": {
        "name": "Tai Mũi Họng",
        "desc": "Tai, mũi, xoang, họng.",
        "keywords": [
            "đau tai", "ù tai", "viêm xoang", "nghẹt mũi", "chảy mũi", "ngứa mũi",
            "khàn tiếng", "amidan", "viêm tai", "nghe kém", "đau họng",
        ],
    },
    "mat": {
        "name": "Mắt",
        "desc": "Bệnh lý về mắt, thị lực.",
        "keywords": [
            "đau mắt", "mờ mắt", "mỏi mắt", "đỏ mắt", "ngứa mắt", "chảy nước mắt",
            "cận thị", "nhức mắt", "khô mắt", "nhìn mờ", "giảm thị lực",
        ],
    },
    "noi_tong_quat": {
        "name": "Nội tổng quát",
        "desc": "Khám tổng quát, triệu chứng chung.",
        "keywords": [
            "sốt", "mệt mỏi", "sụt cân", "ớn lạnh", "chán ăn", "uể oải",
            "khám sức khỏe", "khám tổng quát", "người mệt", "đau người",
        ],
    },
}

# ---------------------------------------------------------------------------
# DANH SÁCH BÁC SĨ theo khoa
# ---------------------------------------------------------------------------
DOCTORS = {
    "tim_mach": [
        {"id": "bs_tm_01", "name": "BS. Nguyễn Văn An"},
        {"id": "bs_tm_02", "name": "BS. Trần Thị Bình"},
    ],
    "ho_hap": [
        {"id": "bs_hh_01", "name": "BS. Lê Minh Châu"},
    ],
    "tieu_hoa": [
        {"id": "bs_th_01", "name": "BS. Phạm Quốc Dũng"},
        {"id": "bs_th_02", "name": "BS. Hoàng Thị Em"},
    ],
    "than_kinh": [
        {"id": "bs_tk_01", "name": "BS. Vũ Đình Phúc"},
    ],
    "co_xuong_khop": [
        {"id": "bs_cxk_01", "name": "BS. Đỗ Thị Giang"},
    ],
    "da_lieu": [
        {"id": "bs_dl_01", "name": "BS. Ngô Văn Hải"},
    ],
    "tai_mui_hong": [
        {"id": "bs_tmh_01", "name": "BS. Bùi Thị Inh"},
    ],
    "mat": [
        {"id": "bs_mat_01", "name": "BS. Dương Văn Khang"},
    ],
    "noi_tong_quat": [
        {"id": "bs_ntq_01", "name": "BS. Lý Thị Lan"},
        {"id": "bs_ntq_02", "name": "BS. Trịnh Văn Minh"},
    ],
}

# Khung giờ làm việc mẫu (giờ bắt đầu mỗi slot 30 phút)
WORK_SLOTS = ["08:00", "08:30", "09:00", "09:30", "10:00",
              "14:00", "14:30", "15:00", "15:30", "16:00"]


def generate_available_slots(num_days: int = 5):
    """Sinh khung giờ trống cho vài ngày tới (bỏ qua Chủ nhật).

    Trả về dict: { 'YYYY-MM-DD': ['08:00', '08:30', ...] }
    Trong thực tế dữ liệu này lấy từ lịch thật của bác sĩ.
    """
    slots = {}
    d = date.today() + timedelta(days=1)  # bắt đầu từ ngày mai
    added = 0
    while added < num_days:
        if d.weekday() != 6:  # 6 = Chủ nhật
            slots[d.isoformat()] = list(WORK_SLOTS)
            added += 1
        d += timedelta(days=1)
    return slots
