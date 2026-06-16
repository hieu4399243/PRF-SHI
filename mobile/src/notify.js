// Local notification + thêm vào Google Calendar.
//
// Local notification (hẹn giờ ngay trên máy) CHẠY ĐƯỢC trong Expo Go, không cần
// server hay EAS, và bắn cả khi app đã tắt. Đây là cách nhắc lịch tin cậy nhất
// cho điện thoại. Khi đặt lịch, ta hẹn sẵn các mốc nhắc; tới giờ máy tự báo.

import { Linking, Platform } from "react-native";
import * as Notifications from "expo-notifications";

function formatDate(iso) {
  const wd = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"];
  const d = new Date(iso + "T00:00:00");
  const day = (d.getDay() + 6) % 7; // JS: 0=CN -> đưa về 0=Thứ 2
  return `${wd[day]}, ${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
}

async function ensurePermission() {
  const cur = await Notifications.getPermissionsAsync();
  if (cur.status === "granted") return true;
  const req = await Notifications.requestPermissionsAsync();
  return req.status === "granted";
}

async function scheduleAt(date, title, body, data) {
  await Notifications.scheduleNotificationAsync({
    content: { title, body, sound: "default", data: data || {} },
    trigger: { type: Notifications.SchedulableTriggerInputTypes.DATE, date },
  });
}

async function scheduleInSeconds(seconds, title, body, data) {
  await Notifications.scheduleNotificationAsync({
    content: { title, body, sound: "default", data: data || {} },
    trigger: { type: Notifications.SchedulableTriggerInputTypes.TIME_INTERVAL, seconds },
  });
}

/**
 * Hẹn các thông báo nhắc cho một lịch hẹn.
 * Trả về số thông báo đã hẹn (để hiển thị cho người dùng biết).
 */
export async function scheduleApptReminders(appt) {
  const ok = await ensurePermission();
  if (!ok) return { scheduled: 0, denied: true };

  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("reminders", {
      name: "Nhắc lịch khám",
      importance: Notifications.AndroidImportance.HIGH,
    });
  }

  const when = `${appt.time} ${formatDate(appt.date)}`;
  const apptTime = new Date(`${appt.date}T${appt.time}:00`).getTime();
  const now = Date.now();
  let scheduled = 0;

  // 1) Xác nhận ngay (sau 3 giây) — để bạn THẤY noti chạy liền.
  await scheduleInSeconds(3, "✅ Đã đặt lịch & bật nhắc",
    `${appt.department} - ${appt.doctor} lúc ${when}. Máy sẽ nhắc bạn trước giờ khám.`,
    { type: "confirm", code: appt.code });
  scheduled++;

  // 2) Các mốc nhắc trước giờ hẹn (chỉ hẹn nếu còn ở tương lai).
  const marks = [
    { before: 24 * 3600 * 1000, title: "📅 Nhắc lịch khám (còn 1 ngày)",
      body: `Ngày mai bạn có lịch khám ${appt.department} - ${appt.doctor} lúc ${when}.` },
    { before: 14 * 3600 * 1000, title: "🍵 Nhắc chăm sóc sức khỏe",
      body: "Trước ngày khám: ăn uống điều độ, uống đủ nước, ngủ sớm, mang theo giấy tờ/thuốc đang dùng." },
    { before: 2 * 3600 * 1000, title: "⏰ Sắp tới giờ khám (còn 2 giờ)",
      body: `Bạn có lịch khám ${appt.department} - ${appt.doctor} lúc ${when}. Đến trước 15 phút nhé.` },
  ];
  for (const m of marks) {
    const at = apptTime - m.before;
    if (at > now + 5000) {
      await scheduleAt(new Date(at), m.title, m.body, { type: "reminder", code: appt.code });
      scheduled++;
    }
  }
  return { scheduled, denied: false };
}

/** Mở Google Calendar với sự kiện điền sẵn — bấm Lưu là vào lịch Google. */
export function addToGoogleCalendar(url) {
  if (url) Linking.openURL(url);
}
