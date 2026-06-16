// Backend trả về reply có chèn HTML nhẹ (<b>, <br>, <a>, <span>).
// React Native không render HTML trực tiếp -> chuyển thành các "đoạn" văn bản
// kèm cờ đậm để hiển thị bằng <Text>. Bỏ qua thẻ link (push lo phần nhắc lịch).

export function htmlToSegments(html) {
  if (!html) return [{ text: "", bold: false }];

  // Chuẩn hóa xuống dòng và bỏ các thẻ không cần.
  let s = html
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/?(span|i|a)[^>]*>/gi, "") // bỏ span/i/a, giữ nội dung
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&nbsp;/g, " ");

  // Tách theo thẻ <b>...</b> để đánh dấu phần in đậm.
  const segments = [];
  const re = /<b>(.*?)<\/b>/gis;
  let last = 0;
  let m;
  while ((m = re.exec(s)) !== null) {
    if (m.index > last) segments.push({ text: s.slice(last, m.index), bold: false });
    segments.push({ text: m[1], bold: true });
    last = re.lastIndex;
  }
  if (last < s.length) segments.push({ text: s.slice(last), bold: false });

  // Dọn các thẻ còn sót (nếu có).
  return segments.map((seg) => ({ ...seg, text: seg.text.replace(/<[^>]+>/g, "") }));
}
