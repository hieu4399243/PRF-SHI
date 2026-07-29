"""
Hiểu bệnh nhân nói gì — "hàm lượng AI" của đề tài.

    engine.py   phân loại triệu chứng -> nhóm dịch vụ (v1 / v2 / llm)
    llm.py      cổng ra mô hình ngôn ngữ (OpenRouter)
    nlu.py      hiểu câu trả lời tự do ở bước đặt lịch (ngày, giờ, tên bác sĩ)
    safety.py   guardrails y tế: cấp cứu, chẩn đoán, PII, audit log

`from app import triage` cho ra đúng API của engine, nên phần còn lại của hệ
thống không cần biết engine nằm ở file nào:

    triage.classify_symptoms("răng tôi ê buốt")

Còn `nlu` và `safety` là hai module riêng, import thẳng:

    from app.triage import nlu, safety
"""

from .engine import (  # noqa: F401
    DEFAULT_VERSION,
    FOLLOWUP_QUESTIONS,
    LLM_VERSION,
    best_department,
    classify_symptoms,
    classify_with_llm,
    clear_llm_cache,
    confidence_level,
    default_version,
    find_service_mention,
    info_question_service,
    is_info_question,
    mentions_dental_discomfort,
    negated_matches,
)
