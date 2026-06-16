// Lớp gọi API tới backend Flask. App native truyền "session" rõ ràng trong body
// (thay vì cookie) để backend tách hội thoại theo từng máy.

import { API_BASE } from "./config";

async function post(path, body) {
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

export function startChat(session) {
  return post("/api/start", { session });
}

export function sendMessage(session, message) {
  return post("/api/chat", { session, message });
}

export function registerPush(session, token) {
  return post("/api/register-push", { session, token });
}
