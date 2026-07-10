# Kết quả đánh giá Triage engine — Nha khoa SHI

- Tập câu ĐƠN-Ý (mỗi câu 1 dịch vụ): **90** câu, **9** lớp (dịch vụ).
- Tập câu PHỨC TẠP (ghép 2-3 ý): **20** câu.
- Sinh tự động bởi `eval/evaluate.py`

## 1. So sánh tổng thể hai phiên bản (tập câu đơn-ý)

| Chỉ số | v1 (có dấu) | v2 (không phân biệt dấu) |
|---|---|---|
| Accuracy (top-1) |  73.3% | ** 97.8%** |
| Accuracy (top-2) |  74.4% | ** 98.9%** |
| Macro Precision |  98.6% | ** 99.0%** |
| Macro Recall |  73.3% | ** 97.8%** |
| Macro F1 |  83.9% | ** 98.3%** |
| Thời gian TB (ms/câu) | 0.020 | 0.162 |

## 2. Precision / Recall / F1 theo từng dịch vụ (v2, tập đơn-ý)

| Dịch vụ | Precision | Recall | F1 | Số mẫu |
|---|---|---|---|---|
| Khám tổng quát & Cạo vôi | 100.0% | 100.0% | 100.0% | 10 |
| Trám răng / Sâu răng |  90.9% | 100.0% |  95.2% | 10 |
| Nội nha (Điều trị tủy) | 100.0% | 100.0% | 100.0% | 10 |
| Nha chu (Nướu / Lợi) | 100.0% | 100.0% | 100.0% | 10 |
| Tiểu phẫu / Nhổ răng | 100.0% | 100.0% | 100.0% | 10 |
| Chỉnh nha (Niềng răng) | 100.0% | 100.0% | 100.0% | 10 |
| Phục hình / Trồng răng | 100.0% |  90.0% |  94.7% | 10 |
| Nha khoa thẩm mỹ | 100.0% | 100.0% | 100.0% | 10 |
| Nha khoa trẻ em | 100.0% |  90.0% |  94.7% | 10 |

## 3. Các trường hợp v2 phân loại sai (error analysis, tập đơn-ý)

| Câu nhập | Nhãn đúng | Dự đoán |
|---|---|---|
| Muốn làm cầu răng sứ cho chỗ răng đã mất | Phục hình / Trồng răng | (không nhận ra) |
| Bé nhà em 6 tuổi bị sâu răng sữa nhiều cái | Nha khoa trẻ em | Trám răng / Sâu răng |

## 4. Tập câu PHỨC TẠP — ghép 2-3 ý (v2)

Mỗi câu nhắc nhiều dịch vụ. `label` là dịch vụ chính; `accept` là mọi dịch vụ hợp lệ được nhắc. Vì bot cho người dùng chọn trong vài gợi ý, ta đo cả top-1 và top-2:

| Chỉ số | Ý nghĩa | Kết quả (v2) |
|---|---|---|
| Top-1 đúng nhãn chính | top-1 == dịch vụ chính |  55.0% |
| Top-1 chấp nhận được | top-1 là một dịch vụ hợp lệ | ** 90.0%** |
| Top-2 chấp nhận được | có dịch vụ hợp lệ trong top-2 | **100.0%** |

Chi tiết từng câu (top-2 dự đoán so với tập dịch vụ hợp lệ):

| Câu ghép nhiều ý | Dịch vụ hợp lệ | Top-2 dự đoán | Top-1 OK | Top-2 OK |
|---|---|---|:--:|:--:|
| Tôi bị chảy máu chân răng, muốn cạo vôi và khám tổng quát luôn | Khám tổng quát & Cạo vôi, Nha chu (Nướu / Lợi) | Khám tổng quát & Cạo vôi > Nha chu (Nướu / Lợi) | ✅ | ✅ |
| Răng khôn mọc lệch đau quá, nhổ xong tôi muốn niềng cho đều | Chỉnh nha (Niềng răng), Tiểu phẫu / Nhổ răng | Tiểu phẫu / Nhổ răng | ✅ | ✅ |
| Con tôi bị sâu răng sữa, tiện thể tôi muốn tẩy trắng răng | Nha khoa trẻ em, Nha khoa thẩm mỹ | Trám răng / Sâu răng > Nha khoa thẩm mỹ | ❌ | ✅ |
| Răng cửa bị mẻ và ố vàng, muốn trám lại và làm trắng răng | Trám răng / Sâu răng, Nha khoa thẩm mỹ | Trám răng / Sâu răng > Nha khoa thẩm mỹ | ✅ | ✅ |
| Tôi bị mất một răng hàm và mấy răng còn lại lung lay do viêm nướu | Nha chu (Nướu / Lợi), Phục hình / Trồng răng | Nha chu (Nướu / Lợi) | ✅ | ✅ |
| Răng sâu đau nhức dữ dội cả đêm, chắc phải lấy tủy | Nội nha (Điều trị tủy), Trám răng / Sâu răng | Trám răng / Sâu răng > Nội nha (Điều trị tủy) | ✅ | ✅ |
| Muốn niềng răng nhưng trước tiên cần cạo vôi và trám chỗ sâu | Chỉnh nha (Niềng răng), Khám tổng quát & Cạo vôi, Trám răng / Sâu răng | Khám tổng quát & Cạo vôi > Chỉnh nha (Niềng răng) | ✅ | ✅ |
| Bị hôi miệng, chảy máu lợi và răng hơi lung lay | Nha chu (Nướu / Lợi) | Nha chu (Nướu / Lợi) | ✅ | ✅ |
| Tôi muốn tẩy trắng răng và dán sứ veneer cho răng cửa | Nha khoa thẩm mỹ | Nha khoa thẩm mỹ | ✅ | ✅ |
| Con tôi đau răng sữa và tôi cũng bị sâu răng muốn khám cùng | Nha khoa trẻ em, Trám răng / Sâu răng | Trám răng / Sâu răng > Nha khoa trẻ em | ✅ | ✅ |
| Răng khôn sưng đau, kèm chảy máu nướu xung quanh | Nha chu (Nướu / Lợi), Tiểu phẫu / Nhổ răng | Nha chu (Nướu / Lợi) > Tiểu phẫu / Nhổ răng | ✅ | ✅ |
| Mất răng lâu ngày muốn trồng implant và niềng cho đều hàm còn lại | Chỉnh nha (Niềng răng), Phục hình / Trồng răng | Phục hình / Trồng răng | ✅ | ✅ |
| Răng vừa hô vừa thưa vừa hơi ố vàng, muốn niềng và tẩy trắng | Chỉnh nha (Niềng răng), Nha khoa thẩm mỹ | Nha khoa thẩm mỹ | ✅ | ✅ |
| Bị áp xe răng đau nhức, nướu sưng to | Nha chu (Nướu / Lợi), Nội nha (Điều trị tủy) | Nội nha (Điều trị tủy) > Trám răng / Sâu răng | ✅ | ✅ |
| Nhức răng về đêm và chảy máu chân răng khi đánh răng | Nha chu (Nướu / Lợi), Nội nha (Điều trị tủy) | Nội nha (Điều trị tủy) > Nha chu (Nướu / Lợi) | ✅ | ✅ |
| Muốn khám tổng quát, cạo vôi và kiểm tra xem có sâu răng không | Khám tổng quát & Cạo vôi, Trám răng / Sâu răng | Khám tổng quát & Cạo vôi > Trám răng / Sâu răng | ✅ | ✅ |
| Răng của bé bị sâu và mọc lệch, có niềng cho trẻ được không | Chỉnh nha (Niềng răng), Nha khoa trẻ em | Nha khoa trẻ em > Trám răng / Sâu răng | ✅ | ✅ |
| con toi bi sau rang sua va rang moc lech muon nieng | Chỉnh nha (Niềng răng), Nha khoa trẻ em | Trám răng / Sâu răng > Nha khoa trẻ em | ❌ | ✅ |
| Răng ê buốt khi ăn lạnh, có lỗ đen và muốn trám sớm | Trám răng / Sâu răng | Trám răng / Sâu răng | ✅ | ✅ |
| toi bi mat rang muon trong implant va boc su rang ben canh | Phục hình / Trồng răng | Phục hình / Trồng răng | ✅ | ✅ |

