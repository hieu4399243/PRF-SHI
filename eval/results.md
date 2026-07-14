# Kết quả đánh giá Triage engine — Nha khoa SHI

- Tập câu ĐƠN-Ý (mỗi câu 1 dịch vụ): **180** câu, **9** lớp (dịch vụ).
- Tập câu PHỨC TẠP (ghép 2-3 ý): **40** câu.
- Sinh tự động bởi `eval/evaluate.py`

## 1. So sánh tổng thể hai phiên bản (tập câu đơn-ý)

| Chỉ số | v1 (có dấu) | v2 (không phân biệt dấu) |
|---|---|---|
| Accuracy (top-1) |  72.8% | **100.0%** |
| Accuracy (top-2) |  72.8% | **100.0%** |
| Macro Precision | 100.0% | **100.0%** |
| Macro Recall |  72.8% | **100.0%** |
| Macro F1 |  84.2% | **100.0%** |
| Thời gian TB (ms/câu) | 0.277 | 0.610 |

## 2. Precision / Recall / F1 theo từng dịch vụ (v2, tập đơn-ý)

| Dịch vụ | Precision | Recall | F1 | Số mẫu |
|---|---|---|---|---|
| Khám tổng quát & Cạo vôi | 100.0% | 100.0% | 100.0% | 20 |
| Trám răng / Sâu răng | 100.0% | 100.0% | 100.0% | 20 |
| Nội nha (Điều trị tủy) | 100.0% | 100.0% | 100.0% | 20 |
| Nha chu (Nướu / Lợi) | 100.0% | 100.0% | 100.0% | 20 |
| Tiểu phẫu / Nhổ răng | 100.0% | 100.0% | 100.0% | 20 |
| Chỉnh nha (Niềng răng) | 100.0% | 100.0% | 100.0% | 20 |
| Phục hình / Trồng răng | 100.0% | 100.0% | 100.0% | 20 |
| Nha khoa thẩm mỹ | 100.0% | 100.0% | 100.0% | 20 |
| Nha khoa trẻ em | 100.0% | 100.0% | 100.0% | 20 |

## 3. Các trường hợp v2 phân loại sai (error analysis, tập đơn-ý)

_Không có lỗi nào trên tập hiện tại._

## 4. Tập câu PHỨC TẠP — ghép 2-3 ý (v2)

Mỗi câu nhắc nhiều dịch vụ. `label` là dịch vụ chính; `accept` là mọi dịch vụ hợp lệ được nhắc. Vì bot cho người dùng chọn trong vài gợi ý, ta đo cả top-1 và top-2:

| Chỉ số | Ý nghĩa | Kết quả (v2) |
|---|---|---|
| Top-1 đúng nhãn chính | top-1 == dịch vụ chính |  52.5% |
| Top-1 chấp nhận được | top-1 là một dịch vụ hợp lệ | ** 97.5%** |
| Top-2 chấp nhận được | có dịch vụ hợp lệ trong top-2 | **100.0%** |

Chi tiết từng câu (top-2 dự đoán so với tập dịch vụ hợp lệ):

| Câu ghép nhiều ý | Dịch vụ hợp lệ | Top-2 dự đoán | Top-1 OK | Top-2 OK |
|---|---|---|:--:|:--:|
| Tôi bị chảy máu chân răng, muốn cạo vôi và khám tổng quát luôn | Khám tổng quát & Cạo vôi, Nha chu (Nướu / Lợi) | Khám tổng quát & Cạo vôi > Nha chu (Nướu / Lợi) | ✅ | ✅ |
| Răng khôn mọc lệch đau quá, nhổ xong tôi muốn niềng cho đều | Chỉnh nha (Niềng răng), Tiểu phẫu / Nhổ răng | Tiểu phẫu / Nhổ răng > Chỉnh nha (Niềng răng) | ✅ | ✅ |
| Con tôi bị sâu răng sữa, tiện thể tôi muốn tẩy trắng răng | Nha khoa trẻ em, Nha khoa thẩm mỹ | Nha khoa thẩm mỹ > Trám răng / Sâu răng | ✅ | ✅ |
| Răng cửa bị mẻ và ố vàng, muốn trám lại và làm trắng răng | Trám răng / Sâu răng, Nha khoa thẩm mỹ | Trám răng / Sâu răng > Nha khoa thẩm mỹ | ✅ | ✅ |
| Tôi bị mất một răng hàm và mấy răng còn lại lung lay do viêm nướu | Nha chu (Nướu / Lợi), Phục hình / Trồng răng | Nha chu (Nướu / Lợi) | ✅ | ✅ |
| Răng sâu đau nhức dữ dội cả đêm, chắc phải lấy tủy | Nội nha (Điều trị tủy), Trám răng / Sâu răng | Trám răng / Sâu răng > Nội nha (Điều trị tủy) | ✅ | ✅ |
| Muốn niềng răng nhưng trước tiên cần cạo vôi và trám chỗ sâu | Chỉnh nha (Niềng răng), Khám tổng quát & Cạo vôi, Trám răng / Sâu răng | Chỉnh nha (Niềng răng) > Khám tổng quát & Cạo vôi | ✅ | ✅ |
| Bị hôi miệng, chảy máu lợi và răng hơi lung lay | Nha chu (Nướu / Lợi) | Nha chu (Nướu / Lợi) | ✅ | ✅ |
| Tôi muốn tẩy trắng răng và dán sứ veneer cho răng cửa | Nha khoa thẩm mỹ | Nha khoa thẩm mỹ | ✅ | ✅ |
| Con tôi đau răng sữa và tôi cũng bị sâu răng muốn khám cùng | Nha khoa trẻ em, Trám răng / Sâu răng | Trám răng / Sâu răng > Nha khoa trẻ em | ✅ | ✅ |
| Răng khôn sưng đau, kèm chảy máu nướu xung quanh | Nha chu (Nướu / Lợi), Tiểu phẫu / Nhổ răng | Nha chu (Nướu / Lợi) > Tiểu phẫu / Nhổ răng | ✅ | ✅ |
| Mất răng lâu ngày muốn trồng implant và niềng cho đều hàm còn lại | Chỉnh nha (Niềng răng), Phục hình / Trồng răng | Phục hình / Trồng răng > Chỉnh nha (Niềng răng) | ✅ | ✅ |
| Răng vừa hô vừa thưa vừa hơi ố vàng, muốn niềng và tẩy trắng | Chỉnh nha (Niềng răng), Nha khoa thẩm mỹ | Nha khoa thẩm mỹ > Chỉnh nha (Niềng răng) | ✅ | ✅ |
| Bị áp xe răng đau nhức, nướu sưng to | Nha chu (Nướu / Lợi), Nội nha (Điều trị tủy) | Nội nha (Điều trị tủy) > Trám răng / Sâu răng | ✅ | ✅ |
| Nhức răng về đêm và chảy máu chân răng khi đánh răng | Nha chu (Nướu / Lợi), Nội nha (Điều trị tủy) | Nội nha (Điều trị tủy) > Nha chu (Nướu / Lợi) | ✅ | ✅ |
| Muốn khám tổng quát, cạo vôi và kiểm tra xem có sâu răng không | Khám tổng quát & Cạo vôi, Trám răng / Sâu răng | Khám tổng quát & Cạo vôi > Trám răng / Sâu răng | ✅ | ✅ |
| Răng của bé bị sâu và mọc lệch, có niềng cho trẻ được không | Chỉnh nha (Niềng răng), Nha khoa trẻ em | Nha khoa trẻ em > Trám răng / Sâu răng | ✅ | ✅ |
| con toi bi sau rang sua va rang moc lech muon nieng | Chỉnh nha (Niềng răng), Nha khoa trẻ em | Trám răng / Sâu răng > Nha khoa trẻ em | ❌ | ✅ |
| Răng ê buốt khi ăn lạnh, có lỗ đen và muốn trám sớm | Trám răng / Sâu răng | Trám răng / Sâu răng | ✅ | ✅ |
| toi bi mat rang muon trong implant va boc su rang ben canh | Phục hình / Trồng răng | Phục hình / Trồng răng | ✅ | ✅ |
| Lợi trùm lên răng gây khó chịu khi nhai | Nha chu (Nướu / Lợi), Tiểu phẫu / Nhổ răng | Tiểu phẫu / Nhổ răng > Nha chu (Nướu / Lợi) | ✅ | ✅ |
| Răng lung lay do chấn thương, không giữ được nữa | Nha chu (Nướu / Lợi), Tiểu phẫu / Nhổ răng | Nha chu (Nướu / Lợi) | ✅ | ✅ |
| Răng vỡ lớn không trám được, bác sĩ khuyên bọc sứ | Phục hình / Trồng răng, Trám răng / Sâu răng | Trám răng / Sâu răng > Phục hình / Trồng răng | ✅ | ✅ |
| Tẩy trắng xong có bị ê buốt không bác sĩ | Trám răng / Sâu răng, Nha khoa thẩm mỹ | Trám răng / Sâu răng > Nha khoa thẩm mỹ | ✅ | ✅ |
| Trẻ bị sâu răng hàm, có trám được không | Nha khoa trẻ em, Trám răng / Sâu răng | Trám răng / Sâu răng > Nha khoa trẻ em | ✅ | ✅ |
| Con tôi ngã va vào răng cửa, răng bị lung lay | Nha chu (Nướu / Lợi), Nha khoa trẻ em | Nha chu (Nướu / Lợi) > Nha khoa trẻ em | ✅ | ✅ |
| Con tôi bị viêm lợi, nướu đỏ và sưng | Nha chu (Nướu / Lợi), Nha khoa trẻ em | Nha chu (Nướu / Lợi) > Nha khoa trẻ em | ✅ | ✅ |
| Trẻ 7 tuổi cần khám răng định kỳ ở đâu | Khám tổng quát & Cạo vôi, Nha khoa trẻ em | Khám tổng quát & Cạo vôi > Nha khoa trẻ em | ✅ | ✅ |
| Vừa muốn cạo vôi vừa muốn tẩy trắng răng cho sáng | Khám tổng quát & Cạo vôi, Nha khoa thẩm mỹ | Nha khoa thẩm mỹ > Khám tổng quát & Cạo vôi | ✅ | ✅ |
| Răng khôn đau nhức dữ dội, nhổ xong có phải lấy tủy không | Tiểu phẫu / Nhổ răng, Nội nha (Điều trị tủy) | Tiểu phẫu / Nhổ răng > Nội nha (Điều trị tủy) | ✅ | ✅ |
| Mất răng hàm lâu rồi, nướu chỗ đó cũng hay sưng | Nha chu (Nướu / Lợi), Phục hình / Trồng răng | Phục hình / Trồng răng > Nha chu (Nướu / Lợi) | ✅ | ✅ |
| Răng sâu vỡ lớn, không biết trám hay bọc sứ thì hơn | Phục hình / Trồng răng, Trám răng / Sâu răng | Trám răng / Sâu răng > Phục hình / Trồng răng | ✅ | ✅ |
| Niềng răng xong muốn tẩy trắng luôn cho đẹp | Chỉnh nha (Niềng răng), Nha khoa thẩm mỹ | Chỉnh nha (Niềng răng) > Nha khoa thẩm mỹ | ✅ | ✅ |
| Chảy máu chân răng nhiều, răng lung lay sợ phải nhổ | Nha chu (Nướu / Lợi), Tiểu phẫu / Nhổ răng | Nha chu (Nướu / Lợi) > Tiểu phẫu / Nhổ răng | ✅ | ✅ |
| Đau răng dữ dội về đêm, có lỗ sâu to ở răng hàm | Nội nha (Điều trị tủy), Trám răng / Sâu răng | Nội nha (Điều trị tủy) > Trám răng / Sâu răng | ✅ | ✅ |
| be bi sau rang sua nhieu, co can tram het khong | Nha khoa trẻ em, Trám răng / Sâu răng | Trám răng / Sâu răng > Nha khoa trẻ em | ✅ | ✅ |
| Muốn khám tổng quát rồi tư vấn niềng răng luôn | Chỉnh nha (Niềng răng), Khám tổng quát & Cạo vôi | Khám tổng quát & Cạo vôi > Chỉnh nha (Niềng răng) | ✅ | ✅ |
| Răng ố vàng lại còn nhiều cao răng bám | Khám tổng quát & Cạo vôi, Nha khoa thẩm mỹ | Nha khoa thẩm mỹ > Khám tổng quát & Cạo vôi | ✅ | ✅ |
| rang da lay tuy roi, gio muon boc su cho chac | Nội nha (Điều trị tủy), Phục hình / Trồng răng | Nội nha (Điều trị tủy) > Phục hình / Trồng răng | ✅ | ✅ |
| Viêm lợi trùm ở răng khôn, sưng đau há miệng khó | Nha chu (Nướu / Lợi), Tiểu phẫu / Nhổ răng | Tiểu phẫu / Nhổ răng > Nha chu (Nướu / Lợi) | ✅ | ✅ |

## 5. Hiểu PHỦ ĐỊNH — “tôi không bị đau răng”

Rule-based chấm điểm theo từ khóa sẽ khớp *“đau răng”* ngay cả khi câu PHỦ ĐỊNH nó. Engine v2 chặn bằng cách bỏ qua từ khóa nằm sau từ phủ định (chỉ nhìn ngược về trước, không vượt qua ranh giới mệnh đề — vì trong tiếng Việt “không” đứng SAU thường là từ để **hỏi**: *“có sâu răng không?”*).

| Chỉ số | Ý nghĩa | v1 | v2 |
|---|---|---|---|
| Không gợi ý nhầm | không đề xuất dịch vụ vừa bị phủ định | 100.0% | **100.0%** |
| Đúng hoàn toàn | không gợi ý nhầm **và** vẫn bắt đúng dịch vụ còn lại | 100.0% | **100.0%** |

| Câu nhập | Dịch vụ bị phủ định | Engine gợi ý | OK |
|---|---|---|:--:|
| tôi không bị đau răng | Nội nha (Điều trị tủy), Trám răng / Sâu răng | (không gợi ý gì) | ✅ |
| rang toi khong bi me vo gi ca | Trám răng / Sâu răng | (không gợi ý gì) | ✅ |
| răng tôi không bị sâu | Trám răng / Sâu răng | (không gợi ý gì) | ✅ |
| tôi không bị áp xe răng | Nội nha (Điều trị tủy) | (không gợi ý gì) | ✅ |
| chưa bị sâu răng bao giờ | Trám răng / Sâu răng | (không gợi ý gì) | ✅ |
| tôi không bị hôi miệng | Nha chu (Nướu / Lợi) | (không gợi ý gì) | ✅ |
| răng không bị lung lay | Nha chu (Nướu / Lợi) | (không gợi ý gì) | ✅ |
| tôi chẳng bị ê buốt gì cả | Trám răng / Sâu răng | (không gợi ý gì) | ✅ |
| khong bi viem loi | Nha chu (Nướu / Lợi) | (không gợi ý gì) | ✅ |
| tôi không muốn niềng răng | Chỉnh nha (Niềng răng) | (không gợi ý gì) | ✅ |
| tôi không bị sâu răng nhưng bị chảy máu chân răng | Trám răng / Sâu răng | Nha chu (Nướu / Lợi) | ✅ |
| không đau răng nhưng nướu sưng và hôi miệng | Nội nha (Điều trị tủy), Trám răng / Sâu răng | Nha chu (Nướu / Lợi) | ✅ |
| răng không mẻ nhưng bị ố vàng muốn tẩy trắng | Trám răng / Sâu răng | Nha khoa thẩm mỹ | ✅ |
| kiểm tra xem có sâu răng không | — | Trám răng / Sâu răng | ✅ |
| nhổ răng khôn có đau không | — | Tiểu phẫu / Nhổ răng | ✅ |
| tẩy trắng răng có hại men răng không | — | Nha khoa thẩm mỹ | ✅ |
| Bác sĩ xem giúp răng em có gì bất thường không, khám tổng quát | — | Khám tổng quát & Cạo vôi | ✅ |
| trồng răng implant có bền không | — | Phục hình / Trồng răng | ✅ |

## 6. Năng lực TỔNG QUÁT HÓA (held-out) — giới hạn của rule-based

| Tập | Cách dùng | Accuracy (v2) | Macro F1 |
|---|---|---|---|
| `dataset.jsonl` | **đã dùng để tinh chỉnh từ khóa** | 100.0% | 100.0% |
| `dataset_heldout.jsonl` | **chưa từng dùng để chỉnh** (câu diễn giải) | ** 37.8%** | ** 49.0%** |

> ⚠️ **Đọc con số cho đúng.** Điểm gần tuyệt đối ở tập trên là điểm *trên chính dữ liệu đã dùng để thêm từ khóa* — nó KHÔNG phải năng lực thật. Con số trung thực là ở tập held-out.

Trong 28 câu sai của tập held-out: **22** câu engine KHÔNG nhận ra gì (bot sẽ hỏi lại — hỏng nhẹ), **6** câu engine đoán SAI dịch vụ (nguy hiểm hơn: dẫn bệnh nhân tới sai bác sĩ).

**Kết luận.** Rule-based chỉ đúng khi người dùng gõ *trúng* từ khóa đã liệt kê. Với câu diễn giải (“buốt tận óc”, “bàn chải dính máu”, “răng chồng lên nhau”) nó mù hoàn toàn. Thêm từ khóa chỉ chữa được phần ngọn — muốn vượt trần này phải dùng NLU theo ngữ nghĩa, tức là điểm cắm LLM `triage.classify_with_llm()`.

| Câu held-out engine bỏ sót / đoán sai | Nhãn đúng | Dự đoán |
|---|---|---|
| Sáu tháng rồi chưa đi nha sĩ, cho tôi hẹn kiểm tra | Khám tổng quát & Cạo vôi | _(không nhận ra)_ |
| nha si xem giup rang em co can lam gi khong | Khám tổng quát & Cạo vôi | _(không nhận ra)_ |
| Muốn nghe tư vấn cách giữ răng miệng sạch sẽ | Khám tổng quát & Cạo vôi | _(không nhận ra)_ |
| rang cua me mot goc nho sau khi can da | Trám răng / Sâu răng | Tiểu phẫu / Nhổ răng |
| Uống trà đá là buốt tận óc, chắc răng có vấn đề | Trám răng / Sâu răng | _(không nhận ra)_ |
| Bác sĩ bảo có chấm đen nhỏ cần hàn sớm kẻo lan | Trám răng / Sâu răng | Tiểu phẫu / Nhổ răng |
| Đau giật từng hồi, đặt lưng xuống là nhức hơn | Nội nha (Điều trị tủy) | Trám răng / Sâu răng |
| Chân răng nổi cục mủ trắng, ấn vào rất đau | Nội nha (Điều trị tủy) | _(không nhận ra)_ |
| bac si hen lam tuy trong ba buoi | Nội nha (Điều trị tủy) | _(không nhận ra)_ |
| Chiếc răng sẫm màu hơn hẳn các răng bên cạnh | Nội nha (Điều trị tủy) | _(không nhận ra)_ |
| Uống giảm đau chỉ đỡ vài tiếng rồi nhức lại | Nội nha (Điều trị tủy) | _(không nhận ra)_ |
| Bàn chải luôn dính máu dù chải rất nhẹ | Nha chu (Nướu / Lợi) | _(không nhận ra)_ |
| Người yêu bảo hơi thở tôi có mùi khó chịu | Nha chu (Nướu / Lợi) | _(không nhận ra)_ |
| Mấy chiếc răng cửa đưa qua đưa lại được bằng lưỡi | Nha chu (Nướu / Lợi) | _(không nhận ra)_ |
| Chiếc răng cuối hàm mọc ngang, đâm vào răng bên | Tiểu phẫu / Nhổ răng | _(không nhận ra)_ |
| rang so tam sung dau nhieu ngay | Tiểu phẫu / Nhổ răng | _(không nhận ra)_ |
| Còn sót mẩu chân răng cũ trong lợi, cần lấy nốt | Tiểu phẫu / Nhổ răng | Nha chu (Nướu / Lợi) |
| Muốn bỏ chiếc răng hư không thể giữ được nữa | Tiểu phẫu / Nhổ răng | _(không nhận ra)_ |
| Hai răng cửa vênh nhau, cười lên trông không đều | Chỉnh nha (Niềng răng) | _(không nhận ra)_ |
| Răng chồng lên nhau vì hàm quá chật | Chỉnh nha (Niềng răng) | _(không nhận ra)_ |
| Chỗ răng rụng bị trống, muốn có răng mới để nhai | Phục hình / Trồng răng | _(không nhận ra)_ |
| ham thao lap cua me bi long roi | Phục hình / Trồng răng | _(không nhận ra)_ |
| Muốn làm mão sứ cho chiếc răng đã chữa tủy | Phục hình / Trồng răng | Nội nha (Điều trị tủy) |
| Muốn hàm răng sáng lên vài tông trước Tết | Nha khoa thẩm mỹ | _(không nhận ra)_ |
| Răng sậm màu vì uống trà lâu năm | Nha khoa thẩm mỹ | _(không nhận ra)_ |
| Có cách nào làm răng đều màu mà không mài nhiều | Nha khoa thẩm mỹ | _(không nhận ra)_ |
| Cháu nhà em hay ngậm cơm, răng cửa mòn hết | Nha khoa trẻ em | Trám răng / Sâu răng |
| con em so ghe nha si, co bac si nhe nhang khong | Nha khoa trẻ em | _(không nhận ra)_ |

