// Cấu hình kết nối tới backend Flask.
//
// QUAN TRỌNG: khi chạy trên điện thoại thật, "localhost" KHÔNG trỏ về máy tính.
// Hãy đổi API_BASE thành địa chỉ IP LAN của máy đang chạy backend, ví dụ:
//   http://192.168.1.10:5000
// Tìm IP máy Mac: System Settings > Wi-Fi > Details, hoặc chạy `ipconfig getifaddr en0`.
// Điện thoại và máy tính phải cùng một mạng Wi-Fi.

export const API_BASE = "http://192.168.2.4:5001";
