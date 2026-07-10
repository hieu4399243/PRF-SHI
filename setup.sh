#!/usr/bin/env bash
#
# Cài đặt & cấu hình môi trường cho AI Health Assistant (SHI).
#
#   ./setup.sh              -> cài backend (Python) + app (npm) + tự dò IP ghi vào config
#   ./setup.sh ip           -> chỉ dò lại IP LAN và cập nhật mobile/src/config.js
#   ./setup.sh backend      -> chỉ cài backend Python
#   ./setup.sh mobile       -> chỉ cài app native (npm)
#
# Tùy chọn qua biến môi trường:
#   IP=192.168.2.4 PORT=5001 ./setup.sh    -> ép IP/cổng thay vì tự dò
#
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PORT="${PORT:-5001}"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
say()  { echo -e "${GREEN}==>${NC} $1"; }
warn() { echo -e "${YELLOW}!! ${NC} $1"; }
err()  { echo -e "${RED}xx ${NC} $1"; }

# --- Dò địa chỉ IP LAN của máy ---
detect_ip() {
  if [ -n "$IP" ]; then echo "$IP"; return; fi
  local ip=""
  if command -v ipconfig >/dev/null 2>&1; then          # macOS
    ip="$(ipconfig getifaddr en0 2>/dev/null || true)"
    [ -z "$ip" ] && ip="$(ipconfig getifaddr en1 2>/dev/null || true)"
  fi
  if [ -z "$ip" ] && command -v hostname >/dev/null 2>&1; then  # Linux
    ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  echo "$ip"
}

# --- Ghi API_BASE vào mobile/src/config.js ---
update_config() {
  local ip="$1"
  if [ -z "$ip" ]; then
    warn "Không tự dò được IP. Hãy sửa tay mobile/src/config.js hoặc chạy: IP=192.168.x.x ./setup.sh ip"
    return
  fi
  local base="http://$ip:$PORT"
  python3 - "$ip" "$PORT" <<'PY'
import re, sys, pathlib
ip, port = sys.argv[1], sys.argv[2]
p = pathlib.Path("mobile/src/config.js")
text = p.read_text(encoding="utf-8")
new = re.sub(r'export const API_BASE = ".*?";',
             f'export const API_BASE = "http://{ip}:{port}";', text)
p.write_text(new, encoding="utf-8")
PY
  say "Đã đặt API_BASE = ${base} (trong mobile/src/config.js)"
}

# --- Cài backend Python ---
setup_backend() {
  command -v python3 >/dev/null 2>&1 || { err "Chưa có python3. Cài Python 3.10+ trước."; exit 1; }
  say "Tạo virtualenv (.venv) và cài thư viện Python..."
  [ -d .venv ] || python3 -m venv .venv
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q -r requirements.txt
  say "Backend sẵn sàng."
}

# --- Cài app native ---
setup_mobile() {
  command -v npm >/dev/null 2>&1 || { err "Chưa có Node/npm. Cài Node 18+ trước (https://nodejs.org)."; exit 1; }
  say "Cài thư viện cho app native (mobile/)..."
  ( cd mobile && npm install )
  say "App native sẵn sàng."
}

print_run() {
  local ip; ip="$(detect_ip)"
  echo ""
  say "HOÀN TẤT. Cách chạy (mở 3 cửa sổ Terminal):"
  echo ""
  echo "  1) Backend:"
  echo "       cd $ROOT && PORT=$PORT ./.venv/bin/python -m app.app"
  echo ""
  echo "  2) Worker nhắc lịch (tùy chọn, cho push qua server):"
  echo "       cd $ROOT && ./.venv/bin/python -m app.reminder_worker --watch"
  echo ""
  echo "  3) App native:"
  echo "       cd $ROOT/mobile && npx expo start -c"
  echo "     -> quét QR bằng Expo Go (điện thoại CÙNG Wi-Fi với máy này)."
  echo ""
  [ -n "$ip" ] && echo "  App đang trỏ tới: http://$ip:$PORT" || warn "Nhớ sửa IP trong mobile/src/config.js"
  echo ""
}

case "${1:-all}" in
  ip)       update_config "$(detect_ip)" ;;
  backend)  setup_backend ;;
  mobile)   setup_mobile ;;
  all|"")   setup_backend; setup_mobile; update_config "$(detect_ip)"; print_run ;;
  *)        err "Tham số không hợp lệ: $1"; echo "Dùng: ./setup.sh [all|ip|backend|mobile]"; exit 1 ;;
esac
