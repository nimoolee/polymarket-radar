#!/bin/zsh
set -e

ROOT="/Users/infinity/Python/Poly_Codex"
UID_VALUE="$(id -u)"

mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$ROOT/logs"

cp "$ROOT/launchd/com.polymonitor.backend.plist" "$HOME/Library/LaunchAgents/com.polymonitor.backend.plist"
cp "$ROOT/launchd/com.polymonitor.frontend.plist" "$HOME/Library/LaunchAgents/com.polymonitor.frontend.plist"

launchctl bootout "gui/$UID_VALUE" "$HOME/Library/LaunchAgents/com.polymonitor.backend.plist" 2>/dev/null || true
launchctl bootout "gui/$UID_VALUE" "$HOME/Library/LaunchAgents/com.polymonitor.frontend.plist" 2>/dev/null || true

launchctl bootstrap "gui/$UID_VALUE" "$HOME/Library/LaunchAgents/com.polymonitor.backend.plist"
launchctl bootstrap "gui/$UID_VALUE" "$HOME/Library/LaunchAgents/com.polymonitor.frontend.plist"
launchctl enable "gui/$UID_VALUE/com.polymonitor.backend"
launchctl enable "gui/$UID_VALUE/com.polymonitor.frontend"
launchctl kickstart -k "gui/$UID_VALUE/com.polymonitor.backend"
launchctl kickstart -k "gui/$UID_VALUE/com.polymonitor.frontend"

echo "PolyMonitor 已安装为后台服务："
echo "- 后端: http://127.0.0.1:8000"
echo "- 前端: http://127.0.0.1:5173"
echo "说明: 页面服务常驻；扫描默认是否启动由 backend/.env 的 SCANNING_ENABLED_DEFAULT 控制。"
echo "如果页面打不开，运行: $ROOT/scripts/ensure_local_services.sh"
