// Ghi lịch hẹn THẲNG vào lịch trên máy bằng expo-calendar.
//
// Khác với việc mở link Google (app không biết bạn có lưu hay không), cách này
// gọi API ghi sự kiện và NHẬN VỀ eventId => app biết chắc đã thêm, và báo lại
// sự kiện nằm ở lịch nào (Google / iCloud / Local). Nếu máy có gắn tài khoản
// Google thì sự kiện vào thẳng Google Calendar và đồng bộ lên đám mây.

import { Platform } from "react-native";
import * as Calendar from "expo-calendar";

const APPT_DURATION_MIN = 30;

async function ensurePermission() {
  const cur = await Calendar.getCalendarPermissionsAsync();
  if (cur.status === "granted") return true;
  const req = await Calendar.requestCalendarPermissionsAsync();
  return req.status === "granted";
}

// Chọn lịch ghi được, ưu tiên tài khoản Google.
async function pickWritableCalendar() {
  const cals = await Calendar.getCalendarsAsync(Calendar.EntityTypes.EVENT);
  const writable = cals.filter((c) => c.allowsModifications);
  if (writable.length === 0) return null;

  const isGoogle = (c) => {
    const src = (c.source && (c.source.name || c.source.type) || "").toLowerCase();
    return src.includes("google") || src.includes("gmail");
  };
  const google = writable.find(isGoogle);
  if (google) return google;

  if (Platform.OS === "ios") {
    try {
      const def = await Calendar.getDefaultCalendarAsync();
      if (def && def.allowsModifications) return def;
    } catch (e) {}
  }
  // Android: ưu tiên lịch chính (isPrimary), nếu không lấy cái đầu.
  return writable.find((c) => c.isPrimary) || writable[0];
}

/**
 * Thêm lịch hẹn vào lịch máy. Trả về:
 *   { ok, eventId, calendarTitle, sourceName }  hoặc  { ok:false, reason }
 */
export async function addAppointmentToCalendar(appt) {
  const granted = await ensurePermission();
  if (!granted) return { ok: false, reason: "denied" };

  const cal = await pickWritableCalendar();
  if (!cal) return { ok: false, reason: "no_calendar" };

  const start = new Date(`${appt.date}T${appt.time}:00`);
  const end = new Date(start.getTime() + APPT_DURATION_MIN * 60 * 1000);

  const eventId = await Calendar.createEventAsync(cal.id, {
    title: `Nha khoa SHI: ${appt.department} - ${appt.doctor}`,
    startDate: start,
    endDate: end,
    location: "Nha khoa SHI",
    notes: `Mã lịch hẹn: ${appt.code}\nĐến trước giờ hẹn 15 phút.`,
    timeZone: "Asia/Ho_Chi_Minh",
    // Lịch tự nhắc trước 1 ngày và trước 2 giờ (thêm 1 lớp thông báo).
    alarms: [{ relativeOffset: -24 * 60 }, { relativeOffset: -2 * 60 }],
  });

  return {
    ok: true,
    eventId,
    calendarTitle: cal.title,
    sourceName: (cal.source && cal.source.name) || "Lịch máy",
  };
}
