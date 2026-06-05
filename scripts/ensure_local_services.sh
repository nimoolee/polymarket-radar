#!/bin/zsh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UID_VALUE="$(id -u)"
AGENT_DIR="$HOME/Library/LaunchAgents"
BACKEND_PLIST="$AGENT_DIR/com.polymonitor.backend.plist"
FRONTEND_PLIST="$AGENT_DIR/com.polymonitor.frontend.plist"

mkdir -p "$AGENT_DIR"
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

if ! launchctl print "gui/$UID_VALUE/com.polymonitor.backend" >/dev/null 2>&1; then
  launchctl bootstrap "gui/$UID_VALUE" "$BACKEND_PLIST"
fi

if ! launchctl print "gui/$UID_VALUE/com.polymonitor.frontend" >/dev/null 2>&1; then
  launchctl bootstrap "gui/$UID_VALUE" "$FRONTEND_PLIST"
fi

launchctl enable "gui/$UID_VALUE/com.polymonitor.backend"
launchctl enable "gui/$UID_VALUE/com.polymonitor.frontend"
launchctl kickstart -k "gui/$UID_VALUE/com.polymonitor.backend"
launchctl kickstart -k "gui/$UID_VALUE/com.polymonitor.frontend"

echo "PolyMonitor 本地页面服务已确保运行。"
echo "- 前端: http://127.0.0.1:5173"
echo "- 后端: http://127.0.0.1:8000"
echo "说明: 页面服务常驻；扫描是否运行由前端开关和 /api/scanner 控制。"
