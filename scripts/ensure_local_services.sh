#!/bin/zsh
set -e

ROOT="/Users/infinity/Python/Poly_Codex"
UID_VALUE="$(id -u)"
AGENT_DIR="$HOME/Library/LaunchAgents"
BACKEND_PLIST="$AGENT_DIR/com.polymonitor.backend.plist"
FRONTEND_PLIST="$AGENT_DIR/com.polymonitor.frontend.plist"

mkdir -p "$AGENT_DIR"
mkdir -p "$ROOT/logs"

cp "$ROOT/launchd/com.polymonitor.backend.plist" "$BACKEND_PLIST"
cp "$ROOT/launchd/com.polymonitor.frontend.plist" "$FRONTEND_PLIST"

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
