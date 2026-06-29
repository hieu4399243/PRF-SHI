# Kết quả đánh giá Triage engine — Nha khoa SHI

- Số mẫu (dataset): **63**
- Số lớp (dịch vụ): **9**
- Sinh tự động bởi `eval/evaluate.py`

## 1. So sánh tổng thể hai phiên bản

| Chỉ số | v1 (có dấu) | v2 (không phân biệt dấu) |
|---|---|---|
| Accuracy |  77.8% | **100.0%** |
| Macro Precision | 100.0% | **100.0%** |
| Macro Recall |  77.8% | **100.0%** |
| Macro F1 |  87.3% | **100.0%** |
| Thời gian TB (ms/câu) | 0.049 | 0.253 |

## 2. Precision / Recall / F1 theo từng dịch vụ (v2)

| Dịch vụ | Precision | Recall | F1 | Số mẫu |
|---|---|---|---|---|
| Khám tổng quát & Cạo vôi | 100.0% | 100.0% | 100.0% | 7 |
| Trám răng / Sâu răng | 100.0% | 100.0% | 100.0% | 7 |
| Nội nha (Điều trị tủy) | 100.0% | 100.0% | 100.0% | 7 |
| Nha chu (Nướu / Lợi) | 100.0% | 100.0% | 100.0% | 7 |
| Tiểu phẫu / Nhổ răng | 100.0% | 100.0% | 100.0% | 7 |
| Chỉnh nha (Niềng răng) | 100.0% | 100.0% | 100.0% | 7 |
| Phục hình / Trồng răng | 100.0% | 100.0% | 100.0% | 7 |
| Nha khoa thẩm mỹ | 100.0% | 100.0% | 100.0% | 7 |
| Nha khoa trẻ em | 100.0% | 100.0% | 100.0% | 7 |

## 3. Các trường hợp v2 phân loại sai (error analysis)

_Không có lỗi nào trên tập hiện tại._

