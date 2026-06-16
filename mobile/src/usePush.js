// Hook xin quyền + lấy device push token (Expo) và đăng ký lên backend.
//
// Nếu chưa cấu hình EAS projectId (chạy demo nhanh), getExpoPushTokenAsync có thể
// lỗi -> ta fallback sang token DEMO để luồng vẫn chạy (backend ghi outbox).
// Khi build thật, điền projectId trong app.json để nhận push trên máy thật.

import { useEffect } from "react";
import { Platform } from "react-native";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { registerPush } from "./api";

// Hiển thị thông báo cả khi app đang mở.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

async function getToken() {
  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("default", {
      name: "default",
      importance: Notifications.AndroidImportance.MAX,
    });
  }

  if (!Device.isDevice) {
    // Máy ảo không nhận được push thật -> token demo để test luồng.
    return "DEMO-EMULATOR-TOKEN";
  }

  const { status: existing } = await Notifications.getPermissionsAsync();
  let status = existing;
  if (existing !== "granted") {
    const req = await Notifications.requestPermissionsAsync();
    status = req.status;
  }
  if (status !== "granted") return null;

  try {
    const tokenData = await Notifications.getExpoPushTokenAsync();
    return tokenData.data; // dạng ExponentPushToken[...]
  } catch (e) {
    // Chưa có projectId/EAS -> dùng token demo để không chặn luồng.
    return "DEMO-NO-PROJECTID-TOKEN";
  }
}

export function usePushRegistration(session) {
  useEffect(() => {
    if (!session) return;
    let active = true;
    (async () => {
      const token = await getToken();
      if (active && token) {
        try {
          await registerPush(session, token);
        } catch (e) {
          // bỏ qua lỗi mạng khi đăng ký token
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [session]);
}
