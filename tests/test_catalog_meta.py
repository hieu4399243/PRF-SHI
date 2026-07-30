"""
Tests cho `SERVICE_META` + `age_group_of()` — dữ liệu tĩnh mà engine gợi ý
(REC-01/02) dựa vào.

Vì sao cần test dữ liệu tĩnh: `SERVICE_META` là overlay khoá theo MÃ dịch vụ, còn
danh mục thật có thể nạp từ Supabase. Lệch mã giữa hai bên không gây exception —
engine chỉ âm thầm mất thời lượng/giá/chu kỳ của dịch vụ đó và card gợi ý hiện
thiếu thông tin. Kiểu lỗi đó phải bị bắt ở test, không phải lúc demo.

Xem docs/patient-recommendation-design.md §6.3.
"""

from datetime import date

from app.core import catalog


# ---------------------------------------------------------------------------
# age_group_of — feature `age_group` (SEQ 4.opt.1)
# ---------------------------------------------------------------------------
TODAY = date(2026, 7, 30)


def test_age_group_moc_bien():
    """Mốc 13 / 18 / 60 tuổi phải rơi đúng nhóm."""
    assert catalog.age_group_of(2026 - 12, TODAY) == "child"
    assert catalog.age_group_of(2026 - 13, TODAY) == "teen"
    assert catalog.age_group_of(2026 - 17, TODAY) == "teen"
    assert catalog.age_group_of(2026 - 18, TODAY) == "adult"
    assert catalog.age_group_of(2026 - 59, TODAY) == "adult"
    assert catalog.age_group_of(2026 - 60, TODAY) == "senior"


def test_age_group_khong_biet_tuoi_tra_none():
    """Không biết năm sinh KHÁC với 'người lớn'. Nếu mặc định thành 'adult', bệnh
    nhân trẻ em chưa khai năm sinh sẽ bị gợi ý dịch vụ người lớn."""
    assert catalog.age_group_of(None, TODAY) is None
    assert catalog.age_group_of("", TODAY) is None
    assert catalog.age_group_of(0, TODAY) is None


def test_age_group_du_lieu_nhap_sai_tra_none():
    """Năm sinh vô lý (nhập tay sai, tương lai, quá 120 tuổi) -> None, không raise."""
    assert catalog.age_group_of("hai ngan", TODAY) is None
    assert catalog.age_group_of(3000, TODAY) is None
    assert catalog.age_group_of(1800, TODAY) is None


def test_age_group_tra_ve_gia_tri_trong_AGE_GROUPS():
    for birth_year in (2020, 2011, 1995, 1950):
        assert catalog.age_group_of(birth_year, TODAY) in catalog.AGE_GROUPS


# ---------------------------------------------------------------------------
# SERVICE_META
# ---------------------------------------------------------------------------
def test_moi_dich_vu_trong_danh_muc_deu_co_meta():
    """Thiếu meta -> card gợi ý mất thời lượng/giá (TC-REC-007 đòi hiện đủ)."""
    thieu = set(catalog.DEPARTMENTS) - set(catalog.SERVICE_META)
    assert not thieu, f"Dịch vụ chưa có SERVICE_META: {sorted(thieu)}"


def test_khong_co_meta_mo_cua_dich_vu_khong_ton_tai():
    """Ngược lại: meta trỏ tới mã không có trong danh mục = mã chết, dấu hiệu
    danh mục đã đổi mà quên cập nhật meta."""
    thua = set(catalog.SERVICE_META) - set(catalog.DEPARTMENTS)
    assert not thua, f"SERVICE_META có mã không còn trong danh mục: {sorted(thua)}"


def test_service_meta_ma_la_tra_ve_mac_dinh_du_khoa():
    """Admin thêm dịch vụ mới trên Supabase -> mã đó chưa có trong SERVICE_META.
    Phải trả dict đủ khoá thay vì KeyError làm sập cả trang gợi ý."""
    meta = catalog.service_meta("dich_vu_moi_chua_khai_bao")
    assert set(meta) == set(catalog.DEFAULT_SERVICE_META)
    assert meta["recurring_months"] is None
    assert meta["age_groups"] == catalog.AGE_GROUPS


def test_service_meta_luon_du_khoa_cho_moi_dich_vu_that():
    for code in catalog.DEPARTMENTS:
        meta = catalog.service_meta(code)
        assert set(meta) == set(catalog.DEFAULT_SERVICE_META), code
        assert meta["duration_min"] > 0, code


def test_gia_hop_le():
    """price_from <= price_to, và không âm."""
    for code in catalog.DEPARTMENTS:
        meta = catalog.service_meta(code)
        lo, hi = meta["price_from"], meta["price_to"]
        assert lo is None or lo >= 0, code
        if lo is not None and hi is not None:
            assert lo <= hi, code


def test_age_groups_chi_chua_gia_tri_hop_le():
    for code in catalog.DEPARTMENTS:
        for group in catalog.service_meta(code)["age_groups"]:
            assert group in catalog.AGE_GROUPS, f"{code}: {group}"


def test_age_affinity_chi_tro_toi_nhom_tuoi_duoc_phep():
    """Cộng điểm cho nhóm tuổi mà chính dịch vụ đó loại trừ = luật tự triệt tiêu
    (chấm điểm cao rồi bị post-filter loại) — luôn là lỗi cấu hình."""
    for code in catalog.DEPARTMENTS:
        meta = catalog.service_meta(code)
        for group in meta["age_affinity"]:
            assert group in meta["age_groups"], f"{code}: affinity '{group}' bị loại trừ"


def test_nha_nhi_chi_danh_cho_tre_em():
    """Gợi ý 'Nha khoa trẻ em' cho người lớn là lỗi nghiệp vụ thấy được ngay."""
    assert catalog.service_meta("nha_nhi")["age_groups"] == ("child",)


def test_dich_vu_khong_dinh_ky_khong_co_chu_ky():
    """Chỉ dịch vụ định kỳ mới được gợi ý lặp lại. Trồng implant / nhổ răng /
    điều trị tủy mà có recurring_months thì engine sẽ nhắc bệnh nhân làm lại."""
    for code in ("noi_nha", "nho_rang", "phuc_hinh", "sau_rang", "chinh_nha"):
        assert catalog.service_meta(code)["recurring_months"] is None, code


def test_dich_vu_dinh_ky_co_chu_ky_hop_ly():
    for code in ("kham_tong_quat", "nha_chu", "tham_my", "nha_nhi"):
        cycle = catalog.service_meta(code)["recurring_months"]
        assert cycle and 1 <= cycle <= 24, code
