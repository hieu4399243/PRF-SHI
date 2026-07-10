"""Tests cho calendar_ics.build_ics() - escape RFC 5545 chống calendar injection."""

import calendar_ics


def _make_appointment(**overrides):
    appointment = {
        "date": "2026-07-15",
        "time": "09:30",
        "code": "SHI-0001",
        "department": "Nha khoa tổng quát",
        "doctor": "BS. Trần Văn A",
        "patient_name": "Nguyễn Văn B",
    }
    appointment.update(overrides)
    return appointment


def test_build_ics_plain_data_unchanged():
    """Dữ liệu thường (không ký tự đặc biệt) phải render y hệt, không backslash thừa."""
    appointment = _make_appointment()
    ics = calendar_ics.build_ics(appointment)

    assert "SUMMARY:Nha khoa SHI: Nha khoa tổng quát - BS. Trần Văn A" in ics
    assert "Mã lịch hẹn: SHI-0001\\n" in ics
    assert "Bệnh nhân: Nguyễn Văn B\\n" in ics
    assert "Dịch vụ: Nha khoa tổng quát\\n" in ics
    assert "Bác sĩ: BS. Trần Văn A\\n" in ics
    assert "UID:SHI-0001@shi-health" in ics


def test_build_ics_escapes_semicolon_comma_backslash():
    appointment = _make_appointment(patient_name="Nguyễn; Văn, A\\B")
    ics = calendar_ics.build_ics(appointment)

    assert "Nguyễn\\; Văn\\, A\\\\B" in ics
    # Chuỗi gốc chưa escape không được xuất hiện.
    assert "Nguyễn; Văn, A\\B" not in ics


def test_build_ics_escapes_newline_in_patient_name():
    appointment = _make_appointment(patient_name="A\nB")
    ics = calendar_ics.build_ics(appointment)

    # Ký tự xuống dòng thật trong patient_name phải bị escape thành literal \n,
    # không được tạo ra dòng vật lý mới phá cấu trúc VEVENT.
    physical_lines = ics.split("\r\n")
    description_lines = [
        line for line in physical_lines if line.startswith("DESCRIPTION:Lịch hẹn")
    ]
    assert len(description_lines) == 1
    assert "A\\nB" in description_lines[0]
    assert "A\nB" not in ics
