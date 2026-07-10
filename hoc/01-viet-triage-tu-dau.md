# Tự viết khối `triage.py` từ con số 0 (cho người mới)

> Mục tiêu: tự tay viết "não AI" phân loại triệu chứng → dịch vụ nha khoa, **gõ tới đâu
> chạy thử tới đó**. Học luôn cú pháp Python căn bản: biến, dict, list, hàm, vòng lặp, if.
>
> Cách dùng tài liệu: mỗi **Bước** bạn thêm code vào 1 file, rồi chạy lệnh ở cuối bước
> để thấy kết quả. Không cần hiểu hết ngay — gõ + chạy + đọc giải thích là ngấm dần.

---

## Chuẩn bị

1. Mở Terminal, vào thư mục dự án:
   ```bash
   cd /Users/hieutm3/Desktop/PRF-SHI
   ```
2. Tạo 1 file mới để tập (KHÔNG sửa file thật `triage.py`):
   ```bash
   touch hoc/triage_demo.py
   ```
3. Mở `hoc/triage_demo.py` trong VS Code. Mỗi bước dưới đây ta sẽ **thêm dần** vào file này.
4. Lệnh chạy file (dùng lại sau mỗi bước):
   ```bash
   ./.venv/bin/python hoc/triage_demo.py
   ```

---

## Bước 0 — Python siêu tốc trong 1 phút

Gõ đoạn này vào `hoc/triage_demo.py` rồi chạy thử:

```python
# Dòng bắt đầu bằng # là CHÚ THÍCH, Python bỏ qua.

ten = "Nha khoa SHI"      # biến kiểu chuỗi (string) — chữ trong dấu " "
so = 5                     # biến kiểu số (int)
danh_sach = ["a", "b"]    # list — danh sách, dùng [ ]
tu_dien = {"ma": "sau_rang", "ten": "Sâu răng"}  # dict — cặp khóa:giá trị, dùng { }

print(ten)                 # print = in ra màn hình
print(danh_sach[0])        # lấy phần tử đầu list (đếm từ 0) → "a"
print(tu_dien["ten"])      # lấy giá trị theo khóa → "Sâu răng"
```

Chạy:
```bash
./.venv/bin/python hoc/triage_demo.py
```
Kỳ vọng in ra:
```
Nha khoa SHI
a
Sâu răng
```

**Nắm 3 thứ:** `list` = danh sách (lấy bằng số thứ tự), `dict` = từ điển (lấy bằng khóa),
`print` = in ra. Cả khối triage chỉ xoay quanh list + dict.

> Sau khi hiểu, **xóa đoạn Bước 0 đi** để file gọn, rồi sang Bước 1.

---

## Bước 1 — Dữ liệu: các dịch vụ và từ khóa

"Não" cần biết: *có những dịch vụ nào, mỗi dịch vụ ứng với từ khóa gì*. Ta mô tả bằng 1 dict
lồng nhau (dict chứa dict).

```python
# Mỗi khóa ("sau_rang"...) là MÃ dịch vụ. Giá trị là 1 dict mô tả dịch vụ đó.
DICH_VU = {
    "sau_rang": {
        "ten": "Trám răng / Sâu răng",
        "tu_khoa": ["sâu răng", "lỗ sâu", "trám răng", "ê buốt", "đau khi nhai"],
    },
    "nha_chu": {
        "ten": "Nha chu (Nướu / Lợi)",
        "tu_khoa": ["chảy máu chân răng", "viêm lợi", "sưng nướu", "hôi miệng"],
    },
    "chinh_nha": {
        "ten": "Chỉnh nha (Niềng răng)",
        "tu_khoa": ["niềng răng", "răng hô", "răng móm", "răng khấp khểnh"],
    },
}

# Thử in ra để kiểm tra
print(DICH_VU["sau_rang"]["ten"])          # → Trám răng / Sâu răng
print(DICH_VU["nha_chu"]["tu_khoa"])       # → danh sách từ khóa nha chu
```

Chạy file. Thấy in đúng nghĩa là cấu trúc dữ liệu ổn.

**Giải thích cú pháp:**
- `DICH_VU` là dict. Mỗi phần tử dạng `"khóa": giá_trị`.
- Giá trị ở đây lại là 1 dict con có 2 khóa: `"ten"` (chuỗi) và `"tu_khoa"` (list các chuỗi).
- `DICH_VU["sau_rang"]["ten"]` = "đi vào ô sau_rang, rồi lấy phần ten".

> Đây chính là `DEPARTMENTS` thu nhỏ trong `data.py` thật.

---

## Bước 2 — Làm sạch câu người dùng

Người ta gõ "Răng tôi SÂU quá!!!" — có chữ hoa, dấu chấm than. Ta cần đưa về dạng chuẩn
"răng tôi sâu quá" để dễ so khớp.

Thêm hàm này (đặt **phía trên** dict `DICH_VU` cũng được, miễn cùng file):

```python
def lam_sach(cau):
    # .lower() = viết thường; .split() = cắt theo khoảng trắng thành list;
    # " ".join(...) = nối lại bằng đúng 1 khoảng trắng (bỏ khoảng trắng thừa).
    return " ".join(cau.lower().split())

# Thử:
print(lam_sach("Răng tôi   SÂU  quá"))   # → "răng tôi sâu quá"
```

**Giải thích:**
- `def ten_ham(thamso):` = định nghĩa 1 **hàm** (một "cỗ máy" nhận đầu vào, trả đầu ra).
- `return` = trả kết quả ra ngoài.
- `cau.lower()` gọi "phương thức" `lower` của chuỗi → chữ thường.
- Hàm giúp tái sử dụng: chỗ nào cần làm sạch chỉ việc gọi `lam_sach(...)`.

> (File thật còn bỏ cả dấu câu bằng regex — ở đây giữ đơn giản cho dễ hiểu.)

---

## Bước 3 — Chấm điểm 1 dịch vụ

Ý tưởng cốt lõi: **đếm xem câu chứa bao nhiêu từ khóa của dịch vụ đó**. Càng nhiều → điểm
càng cao.

```python
def cham_diem(cau_sach, tu_khoa_list):
    diem = 0
    trung = []                      # list lưu các từ khóa đã trúng (để giải thích)
    for kw in tu_khoa_list:         # duyệt từng từ khóa
        if kw in cau_sach:          # "kw in chuoi" = chuỗi có chứa kw không?
            diem = diem + 1         # trúng thì cộng 1 điểm
            trung.append(kw)        # ghi lại từ trúng
    return diem, trung              # trả về 2 giá trị cùng lúc

# Thử:
cau = lam_sach("tôi bị sâu răng và ê buốt khi ăn")
print(cham_diem(cau, DICH_VU["sau_rang"]["tu_khoa"]))   # → (2, ['sâu răng', 'ê buốt'])
```

**Giải thích:**
- `for kw in danh_sach:` = **vòng lặp**, lần lượt gán mỗi phần tử cho biến `kw`.
- `if dieu_kien:` = nếu đúng thì làm phần thụt vào bên dưới.
- `"sâu răng" in "tôi bị sâu răng..."` trả về `True` (có chứa).
- `.append(x)` = thêm x vào cuối list.
- Hàm này trả **2 thứ** (điểm và list trúng) — Python cho phép `return a, b`.

---

## Bước 4 — Chấm điểm TẤT CẢ dịch vụ rồi xếp hạng

```python
def phan_loai(cau_nguoi_dung):
    cau = lam_sach(cau_nguoi_dung)
    ket_qua = []                                  # list các dịch vụ có điểm > 0

    for ma, dv in DICH_VU.items():                # .items() = duyệt cả khóa lẫn giá trị
        diem, trung = cham_diem(cau, dv["tu_khoa"])
        if diem > 0:
            ket_qua.append({                      # thêm 1 dict kết quả
                "ma": ma,
                "ten": dv["ten"],
                "diem": diem,
                "trung": trung,
            })

    # Sắp xếp: điểm cao lên đầu. key=... bảo "sắp theo trường diem"; reverse=True = giảm dần
    ket_qua.sort(key=lambda r: r["diem"], reverse=True)
    return ket_qua

# Thử:
for kq in phan_loai("tôi bị sâu răng và hôi miệng"):
    print(kq["ten"], "→", kq["diem"], "điểm", kq["trung"])
```

Chạy, kỳ vọng đại loại:
```
Trám răng / Sâu răng → 1 điểm ['sâu răng']
Nha chu (Nướu / Lợi) → 1 điểm ['hôi miệng']
```

**Giải thích chỗ khó:**
- `DICH_VU.items()` trả từng cặp `(khóa, giá_trị)` → ta hứng vào 2 biến `ma, dv`.
- `ket_qua.sort(key=lambda r: r["diem"], reverse=True)`:
  - `sort` = sắp xếp list tại chỗ.
  - `lambda r: r["diem"]` = "hàm 1 dòng" nói rằng *với mỗi phần tử r, lấy r["diem"] để so sánh*.
  - `reverse=True` = từ lớn đến nhỏ.

---

## Bước 5 — Lấy đáp án tốt nhất

```python
def tot_nhat(cau_nguoi_dung):
    kq = phan_loai(cau_nguoi_dung)
    if kq:                 # list không rỗng?
        return kq[0]       # phần tử đầu = điểm cao nhất
    return None            # không trúng gì → None (rỗng)

# Thử:
print(tot_nhat("muốn niềng răng vì răng hô"))   # → dịch vụ Chỉnh nha
print(tot_nhat("xyz không liên quan"))           # → None
```

**Giải thích:** `if kq:` — trong Python, list rỗng coi như "sai (False)", list có phần tử là
"đúng (True)". Nên `if kq:` nghĩa là "nếu có kết quả".

---

## Bước 6 — Đóng gói để chạy thử nhiều câu

Thêm xuống **cuối file**:

```python
if __name__ == "__main__":
    cac_cau_thu = [
        "tôi bị sâu răng và ê buốt",
        "chảy máu chân răng, hôi miệng",
        "muốn niềng răng",
        "trời hôm nay đẹp",
    ]
    for c in cac_cau_thu:
        kq = tot_nhat(c)
        ten = kq["ten"] if kq else "KHÔNG NHẬN RA"
        print(f"'{c}'  →  {ten}")
```

Chạy:
```bash
./.venv/bin/python hoc/triage_demo.py
```
Kỳ vọng:
```
'tôi bị sâu răng và ê buốt'  →  Trám răng / Sâu răng
'chảy máu chân răng, hôi miệng'  →  Nha chu (Nướu / Lợi)
'muốn niềng răng'  →  Chỉnh nha (Niềng răng)
'trời hôm nay đẹp'  →  KHÔNG NHẬN RA
```

**Giải thích 2 thứ hay gặp:**
- `if __name__ == "__main__":` = "chỉ chạy đoạn này khi gọi trực tiếp file, không chạy khi
  file bị import nơi khác". Rất phổ biến trong Python.
- `f"'{c}' → {ten}"` = **f-string**: nhét giá trị biến vào chuỗi bằng `{ }`.

🎉 Bạn vừa tự viết xong một bộ phân loại AND nó chạy! Đây đúng là tinh thần của `triage.py` thật.

---

## Bước 7 (nâng cao) — Hiểu tiếng Việt KHÔNG DẤU

Thử `tot_nhat("toi bi sau rang")` (không dấu) → hiện tại ra `KHÔNG NHẬN RA`, vì "sau rang"
≠ "sâu răng". Đây là lý do file thật có **phiên bản v2 bỏ dấu**.

Thêm hàm bỏ dấu và dùng nó khi so khớp:

```python
import unicodedata   # đặt ở ĐẦU file

def bo_dau(s):
    s = s.replace("đ", "d")                                  # đ → d
    s = unicodedata.normalize("NFD", s)                      # tách chữ và dấu
    return "".join(c for c in s if unicodedata.category(c) != "Mn")  # bỏ ký tự dấu

print(bo_dau("sâu răng"))   # → "sau rang"
```

Rồi sửa `cham_diem` để khớp cả bản không dấu:
```python
def cham_diem(cau_sach, tu_khoa_list):
    diem, trung = 0, []
    cau_khong_dau = bo_dau(cau_sach)
    for kw in tu_khoa_list:
        if kw in cau_sach or bo_dau(kw) in cau_khong_dau:   # thêm điều kiện không dấu
            diem += 1                                        # += là cách viết gọn của diem = diem + 1
            trung.append(kw)
    return diem, trung
```

Giờ `tot_nhat("toi bi sau rang")` sẽ ra **Trám răng / Sâu răng**. Đó chính là cải tiến giúp
v2 đạt 98.4% so với v1 76.2% trong báo cáo đánh giá của bạn.

> ⚠️ File thật còn 1 lớp nữa: khớp theo **ranh giới từ** (thêm khoảng trắng 2 đầu) để
> tránh "c**hân răng**" (bỏ dấu = "chan rang") nuốt nhầm "hàn răng" (= "han rang"). Khi
> nào vững, mở `triage.py` đọc hàm `_contains_word` sẽ hiểu.

---

## Nối vào dự án thật như thế nào?

File thật khác bản demo này ở chỗ:
1. Lấy dữ liệu từ `data.py` (`from data import DEPARTMENTS`) thay vì viết dict tại chỗ.
2. Tên trường tiếng Anh: `name`, `desc`, `keywords`, `code` (thay cho `ten`, `tu_khoa`, `ma`).
3. Cụm từ dài được +2 điểm (đáng tin hơn từ đơn).
4. Có thêm `confidence_level()` để chatbot biết khi nào nên hỏi lại.
5. **Fallback "than phiền nha khoa chung"** — `mentions_dental_discomfort()`: câu có nhắc
   **bộ phận** răng miệng ("răng", "nướu", "hàm"…) + một **cảm giác** khó chịu ("đau",
   "ê", "nhức", "khi nhai"…) nhưng không trúng từ khóa dịch vụ nào → thay vì bó tay báo
   "chưa rõ", chatbot đưa **danh sách dịch vụ** để người dùng tự chọn (hỏi có cấu trúc).
6. **Câu hỏi thông tin** — `is_info_question()` + `find_service_mention()`: nhận ra
   *"trám răng là khám gì?"*, *"nội nha gồm những gì?"* là câu **hỏi thông tin** (không
   phải than phiền) → trả về **mô tả dịch vụ** đó thay vì cố phân loại triệu chứng.
   Mẹo: so khớp bằng **tập token** đã bỏ các từ quá chung ("răng", "khám", "gì"…),
   ưu tiên khớp có dấu trước ("trồng" ≠ "trong") rồi mới thử bản không dấu.

Đối chiếu bản bạn vừa viết với [triage.py](../app/triage.py) — bạn sẽ thấy **cùng một ý tưởng**,
chỉ "mặc áo chỉnh tề" hơn.

---

## Bài tập tự làm (để chắc đã hiểu)
1. Thêm 1 dịch vụ mới vào `DICH_VU`, ví dụ `tham_my` với từ khóa `["tẩy trắng", "răng ố vàng"]`,
   rồi thử câu "muốn tẩy trắng răng".
2. Cho cụm 2 chữ +2 điểm, từ đơn +1 (gợi ý: `2 if " " in kw else 1`).
3. In ra **cả 3 dịch vụ điểm cao nhất** thay vì chỉ 1 (gợi ý: `phan_loai(cau)[:3]`).

Làm xong bài 1–3 là bạn đã nắm chắc khối triage. Muốn tôi viết tiếp tài liệu kiểu này cho
**`chatbot.py` (máy trạng thái)** — khối người mới hay rối nhất — thì nói nhé.
