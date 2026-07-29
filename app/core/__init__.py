"""
Hạ tầng dùng chung — không chứa logic hội thoại, không biết gì về chatbot.

    catalog.py   danh mục dịch vụ (DEPARTMENTS) + bác sĩ (DOCTORS) + khung giờ
    storage.py   lớp lưu trữ: có DATABASE_URL -> Postgres, không -> file JSON
    text.py      chuẩn hóa/bỏ dấu tiếng Việt, dùng chung cho triage & nlu & safety
"""
