"""
Trích feature vector từ lịch sử điều trị — bước 4.opt.1 của SEQ-S2-Recommendation.

Đúng bộ feature mà spec liệt kê: `age_group`, `time_since_last`,
`followup_overdue`, `category_distribution`, `allergy_flags` (+ `visit_count` để
quyết định nhánh cold-start).

Hàm THUẦN: nhận list lịch sử + profile, không đọc DB, không gọi mạng.
"""

from datetime import date

from ..core.catalog import age_group_of, service_meta


def _days_between(iso_a, iso_b):
    try:
        return (date.fromisoformat(iso_a) - date.fromisoformat(iso_b)).days
    except (TypeError, ValueError):
        return None


def _months_between(iso_a, iso_b):
    """Số tháng (làm tròn xuống) giữa hai ngày ISO. None nếu ngày không hợp lệ."""
    days = _days_between(iso_a, iso_b)
    return None if days is None else int(days // 30.44)


def build(history, profile=None, today=None):
    """Dựng feature vector.

    Args:
        history: list bản ghi điều trị, MỚI NHẤT TRƯỚC (xem reco/history.recent)
        profile: {"birth_year": int|None, "allergies": [str]}
        today: date, để test cố định thời gian

    Returns:
        dict feature — cũng chính là `feature_snapshot` ghi vào recommendation_log,
        nên mọi giá trị phải serialize được sang JSON.
    """
    profile = profile or {}
    today = today or date.today()
    today_iso = today.isoformat()

    dates = [r.get("treatment_date") for r in history if r.get("treatment_date")]
    last_date = max(dates) if dates else None

    # Lần gần nhất của TỪNG dịch vụ — luật chu kỳ cần mốc riêng cho mỗi dịch vụ,
    # không phải mốc chung của cả hồ sơ.
    last_by_service = {}
    for rec in history:
        code, d = rec.get("service_code"), rec.get("treatment_date")
        if code and d and d > last_by_service.get(code, ""):
            last_by_service[code] = d

    category_distribution = {}
    for rec in history:
        code = rec.get("service_code")
        if code:
            category_distribution[code] = category_distribution.get(code, 0) + 1

    # Tái khám quá hạn: nha sĩ đã ghi rõ followup_due_date và ngày đó đã trôi qua.
    # Đây là tín hiệu MẠNH NHẤT vì nó là chỉ định của người, không phải suy luận.
    overdue = []
    for rec in history:
        if not rec.get("followup_required"):
            continue
        due = rec.get("followup_due_date")
        if due and due < today_iso:
            overdue.append({
                "service_code": rec.get("service_code"),
                "due_date": due,
                "overdue_months": _months_between(today_iso, due) or 0,
            })
    # Quá hạn lâu nhất lên đầu -> luật lấy cái cấp thiết nhất.
    overdue.sort(key=lambda o: o["overdue_months"], reverse=True)

    return {
        "visit_count": len(history),
        "last_treatment_date": last_date,
        "time_since_last": _days_between(today_iso, last_date) if last_date else None,
        "months_since_last": _months_between(today_iso, last_date) if last_date else None,
        "followup_overdue": bool(overdue),
        "overdue": overdue,
        "category_distribution": category_distribution,
        "last_by_service": last_by_service,
        "services_used": sorted(last_by_service),
        "age_group": age_group_of(profile.get("birth_year"), today),
        "allergy_flags": list(profile.get("allergies") or []),
        "today": today_iso,
    }


def months_since_service(features, service_code):
    """Số tháng kể từ lần gần nhất dùng một dịch vụ. None nếu chưa từng dùng."""
    last = features.get("last_by_service", {}).get(service_code)
    if not last:
        return None
    return _months_between(features["today"], last)


def is_recurring_due(features, service_code):
    """Dịch vụ định kỳ đã tới/quá chu kỳ khuyến nghị chưa?

    Trả (đã tới hạn, số tháng kể từ lần cuối, chu kỳ). Dịch vụ không định kỳ ->
    (False, ..., None): không ai cần trồng lại implant theo chu kỳ.
    """
    cycle = service_meta(service_code)["recurring_months"]
    months = months_since_service(features, service_code)
    if not cycle or months is None:
        return False, months, cycle
    return months >= cycle, months, cycle


def snapshot(features):
    """Bản gọn để ghi vào `recommendation_log.feature_snapshot`.

    Cố tình KHÔNG ghi `last_by_service` / `category_distribution` đầy đủ: log là
    append-only và giữ lâu, không cần lưu lại toàn bộ hồ sơ điều trị của bệnh nhân
    ở đó (giảm bề mặt dữ liệu cá nhân bị nhân bản).
    """
    return {
        "visit_count": features.get("visit_count"),
        "time_since_last": features.get("time_since_last"),
        "followup_overdue": features.get("followup_overdue"),
        "age_group": features.get("age_group"),
        "n_services_used": len(features.get("services_used") or []),
        "has_allergy_data": bool(features.get("allergy_flags")),
    }
