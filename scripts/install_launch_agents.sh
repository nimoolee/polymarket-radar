#!/bin/zsh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UID_VALUE="$(id -u)"
BACKEND_PLIST="$HOME/Library/LaunchAgents/com.polymonitor.backend.plist"
FRONTEND_PLIST="$HOME/Library/LaunchAgents/com.polymonitor.frontend.plist"

mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$ROOT/logs"

cat > "$BACKEND_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.polymonitor.backend</string>
  <key>ProgramArguments</key>
  <array>
    <string>$ROOT/scripts/start_backend.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT/backend</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$ROOT/logs/backend.out.log</string>
  <key>StandardErrorPath</key>
  <string>$ROOT/logs/backend.err.log</string>
</dict>
</plist>
EOF

cat > "$FRONTEND_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.polymonitor.frontend</string>
  <key>ProgramArguments</key>
  <array>
    <string>$ROOT/scripts/start_frontend.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT/frontend</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$ROOT/logs/frontend.out.log</string>
  <key>StandardErrorPath</key>
  <string>$ROOT/logs/frontend.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$UID_VALUE" "$BACKEND_PLIST" 2>/dev/null || true
launchctl bootout "gui/$UID_VALUE" "$FRONTEND_PLIST" 2>/dev/null || true

launchctl bootstrap "gui/$UID_VALUE" "$BACKEND_PLIST"
launchctl bootstrap "gui/$UID_VALUE" "$FRONTEND_PLIST"
launchctl enable "gui/$UID_VALUE/com.polymonitor.backend"
launchctl enable "gui/$UID_VALUE/com.polymonitor.frontend"
launchctl kickstart -k "gui/$UID_VALUE/com.polymonitor.backend"
launchctl kickstart -k "gui/$UID_VALUE/com.polymonitor.frontend"

echo "PolyMonitor 已安装为后台服务："
echo "- 后端: http://127.0.0.1:8000"
echo "- 前端: http://127.0.0.1:5173"
echo "说明: 页面服务常驻；扫描默认是否启动由 backend/.env 的 SCANNING_ENABLED_DEFAULT 控制。"
echo "如果页面打不开，运行: $ROOT/scripts/ensure_local_services.sh"
