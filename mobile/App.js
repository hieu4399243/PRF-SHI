import React, { useEffect, useRef, useState } from "react";
import {
  SafeAreaView, View, Text, TextInput, TouchableOpacity, ScrollView,
  KeyboardAvoidingView, Platform, StyleSheet, ActivityIndicator,
} from "react-native";
import { StatusBar } from "expo-status-bar";
import AsyncStorage from "@react-native-async-storage/async-storage";

import { startChat, sendMessage } from "./src/api";
import { usePushRegistration } from "./src/usePush";
import { htmlToSegments } from "./src/html";
import { scheduleApptReminders } from "./src/notify";
import { addAppointmentToCalendar } from "./src/calendar";

// Tạo / lấy lại session id ổn định cho thiết bị (để push & lịch hẹn khớp nhau).
async function getSession() {
  let sid = await AsyncStorage.getItem("shi_session");
  if (!sid) {
    sid = "dev-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    await AsyncStorage.setItem("shi_session", sid);
  }
  return sid;
}

// Một bong bóng tin nhắn (render văn bản có in đậm từ HTML backend).
function Bubble({ item }) {
  const isBot = item.who === "bot";
  const segments = htmlToSegments(item.text);
  return (
    <View style={[styles.row, isBot ? styles.rowBot : styles.rowUser]}>
      {isBot && <Text style={styles.miniAvatar}>🤖</Text>}
      <View style={[styles.bubble, isBot ? styles.bubbleBot : styles.bubbleUser]}>
        <Text style={isBot ? styles.bubbleTextBot : styles.bubbleTextUser}>
          {segments.map((s, i) => (
            <Text key={i} style={s.bold ? styles.bold : null}>{s.text}</Text>
          ))}
        </Text>
      </View>
      {!isBot && <Text style={styles.miniAvatar}>🙂</Text>}
    </View>
  );
}

export default function App() {
  const [session, setSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [options, setOptions] = useState([]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [calendarAppt, setCalendarAppt] = useState(null); // lịch hẹn vừa đặt
  const scrollRef = useRef(null);

  usePushRegistration(session); // xin quyền + đăng ký device token

  // Khởi tạo phiên + lời chào.
  useEffect(() => {
    (async () => {
      const sid = await getSession();
      setSession(sid);
      setTyping(true);
      try {
        const data = await startChat(sid);
        setMessages([{ who: "bot", text: data.reply }]);
        setOptions(data.options || []);
      } catch (e) {
        setMessages([{ who: "bot", text: "Không kết nối được máy chủ. Kiểm tra API_BASE trong src/config.js." }]);
      } finally {
        setTyping(false);
      }
    })();
  }, []);

  const scrollDown = () =>
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 60);

  // Ghi lịch hẹn vào lịch máy và BÁO LẠI kết quả (để biết chắc đã thêm).
  async function onAddToCalendar(appt) {
    setMessages((m) => [...m, { who: "bot", text: "Đang thêm vào lịch…" }]);
    try {
      const res = await addAppointmentToCalendar(appt);
      let msg;
      if (res.ok) {
        msg = `✅ <b>Đã thêm vào lịch thành công.</b><br>Sự kiện nằm trong lịch "<b>${res.calendarTitle}</b>" `
            + `(nguồn: ${res.sourceName}). Mở app Lịch / Google Calendar để xem. Lịch sẽ tự nhắc trước 1 ngày và 2 giờ.`;
      } else if (res.reason === "denied") {
        msg = "⚠️ Bạn chưa cho phép truy cập Lịch nên chưa thêm được. Vào Cài đặt → cấp quyền Lịch rồi thử lại.";
      } else {
        msg = "⚠️ Không tìm thấy lịch ghi được trên máy. Hãy thêm một tài khoản lịch (vd. Google) trong Cài đặt.";
      }
      setMessages((m) => [...m, { who: "bot", text: msg }]);
    } catch (e) {
      setMessages((m) => [...m, { who: "bot", text: "⚠️ Có lỗi khi thêm vào lịch. Vui lòng thử lại." }]);
    }
    setCalendarAppt(null);
    scrollDown();
  }

  async function send(text, displayLabel) {
    if (!text || !session) return;
    setOptions([]);
    setCalendarAppt(null);
    setMessages((m) => [...m, { who: "user", text: displayLabel || text }]);
    setInput("");
    scrollDown();
    setTyping(true);
    try {
      const data = await sendMessage(session, text);
      await new Promise((r) => setTimeout(r, 350)); // cảm giác đang gõ
      setMessages((m) => [...m, { who: "bot", text: data.reply }]);
      setOptions(data.options || []);

      // Đặt lịch thành công -> hẹn local notification + hiện nút thêm lịch.
      if (data.appointment) {
        setCalendarAppt(data.appointment);
        try {
          const res = await scheduleApptReminders(data.appointment);
          const note = res.denied
            ? "⚠️ Bạn chưa cho phép thông báo nên không bật được nhắc lịch. Vào Cài đặt để bật nhé."
            : `🔔 Đã bật ${res.scheduled} thông báo nhắc trên máy (xác nhận ngay + nhắc trước giờ khám).`;
          setMessages((m) => [...m, { who: "bot", text: note }]);
        } catch (e) {
          // bỏ qua nếu hẹn thông báo lỗi
        }
      }
    } catch (e) {
      setMessages((m) => [...m, { who: "bot", text: "Xin lỗi, có lỗi kết nối. Vui lòng thử lại." }]);
    } finally {
      setTyping(false);
      scrollDown();
    }
  }

  return (
    <SafeAreaView style={styles.app}>
      <StatusBar style="light" />

      {/* Header */}
      <View style={styles.head}>
        <View style={styles.avatar}><Text style={{ fontSize: 22 }}>🦷</Text></View>
        <View style={{ flex: 1 }}>
          <Text style={styles.headTitle}>Trợ lý Nha khoa SHI</Text>
          <Text style={styles.headSub}>Chọn dịch vụ nha khoa & Đặt lịch hẹn</Text>
        </View>
        <View style={styles.statusWrap}>
          <View style={styles.dot} />
          <Text style={styles.statusText}>Online</Text>
        </View>
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={Platform.OS === "ios" ? 0 : 0}
      >
        {/* Tin nhắn */}
        <ScrollView
          ref={scrollRef}
          style={styles.msgs}
          contentContainerStyle={{ padding: 16, gap: 12 }}
          onContentSizeChange={scrollDown}
        >
          {messages.map((item, i) => <Bubble key={i} item={item} />)}

          {typing && (
            <View style={[styles.row, styles.rowBot]}>
              <Text style={styles.miniAvatar}>🤖</Text>
              <View style={[styles.bubble, styles.bubbleBot, { flexDirection: "row", alignItems: "center" }]}>
                <ActivityIndicator size="small" color="#0e9b8e" />
                <Text style={{ color: "#8a8a8a", marginLeft: 8 }}>đang trả lời…</Text>
              </View>
            </View>
          )}

          {/* Nút chọn nhanh */}
          {options.length > 0 && (
            <View style={styles.options}>
              {options.map((o, i) => (
                <TouchableOpacity key={i} style={styles.opt} onPress={() => send(o.value, o.label)}>
                  <Text style={styles.optText}>{o.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
          )}

          {/* Nút thêm vào Google Calendar sau khi đặt lịch */}
          {calendarAppt && (
            <TouchableOpacity
              style={styles.calBtn}
              onPress={() => onAddToCalendar(calendarAppt)}
            >
              <Text style={styles.calBtnText}>📆 Thêm vào lịch (Google/iCloud)</Text>
            </TouchableOpacity>
          )}
        </ScrollView>

        {/* Ô nhập */}
        <View style={styles.inputBar}>
          <TextInput
            style={styles.input}
            placeholder="Mô tả vấn đề răng miệng của bạn..."
            placeholderTextColor="#9aa6a4"
            value={input}
            onChangeText={setInput}
            onSubmitEditing={() => send(input.trim())}
            returnKeyType="send"
          />
          <TouchableOpacity
            style={[styles.send, !input.trim() && { opacity: 0.5 }]}
            onPress={() => send(input.trim())}
            disabled={!input.trim()}
          >
            <Text style={{ color: "#fff", fontSize: 18 }}>➤</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const TEAL = "#0e9b8e";
const TEAL_DEEP = "#0b7d72";
const TEAL_TINT = "#e7f4f1";

const styles = StyleSheet.create({
  app: { flex: 1, backgroundColor: "#f6f8f8" },
  head: {
    backgroundColor: TEAL, flexDirection: "row", alignItems: "center",
    paddingHorizontal: 16, paddingVertical: 14, gap: 12,
  },
  avatar: {
    width: 42, height: 42, borderRadius: 21,
    backgroundColor: "rgba(255,255,255,0.18)", alignItems: "center", justifyContent: "center",
  },
  headTitle: { color: "#fff", fontSize: 16, fontWeight: "700" },
  headSub: { color: "rgba(255,255,255,0.9)", fontSize: 11, marginTop: 2 },
  statusWrap: { flexDirection: "row", alignItems: "center", gap: 6 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: "#7CFFB2" },
  statusText: { color: "#fff", fontSize: 11 },

  msgs: { flex: 1 },
  row: { flexDirection: "row", alignItems: "flex-end", maxWidth: "92%", gap: 6 },
  rowBot: { alignSelf: "flex-start" },
  rowUser: { alignSelf: "flex-end", flexDirection: "row" },
  miniAvatar: { fontSize: 20, marginBottom: 2 },
  bubble: {
    paddingHorizontal: 14, paddingVertical: 10, borderRadius: 16, maxWidth: "86%",
    shadowColor: "#000", shadowOpacity: 0.05, shadowRadius: 2, shadowOffset: { width: 0, height: 1 },
  },
  bubbleBot: { backgroundColor: "#fff", borderBottomLeftRadius: 4 },
  bubbleUser: { backgroundColor: TEAL, borderBottomRightRadius: 4 },
  bubbleTextBot: { color: "#2e2e2e", fontSize: 14.5, lineHeight: 21 },
  bubbleTextUser: { color: "#fff", fontSize: 14.5, lineHeight: 21 },
  bold: { fontWeight: "700" },

  options: { flexDirection: "row", flexWrap: "wrap", gap: 8, alignSelf: "flex-start", maxWidth: "92%" },
  opt: {
    borderWidth: 1.5, borderColor: TEAL, backgroundColor: "#fff",
    paddingHorizontal: 13, paddingVertical: 8, borderRadius: 20,
  },
  optText: { color: TEAL_DEEP, fontSize: 13, fontWeight: "600" },
  calBtn: {
    alignSelf: "flex-start", backgroundColor: TEAL_TINT, borderWidth: 1, borderColor: TEAL,
    paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12,
  },
  calBtnText: { color: TEAL_DEEP, fontSize: 13.5, fontWeight: "700" },

  inputBar: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingHorizontal: 12, paddingVertical: 10,
    borderTopWidth: 1, borderTopColor: "#e4e4e4", backgroundColor: "#fff",
  },
  input: {
    flex: 1, borderWidth: 1.5, borderColor: "#e4e4e4", borderRadius: 22,
    paddingHorizontal: 16, paddingVertical: Platform.OS === "ios" ? 11 : 8, fontSize: 14.5,
  },
  send: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: TEAL,
    alignItems: "center", justifyContent: "center",
  },
});
