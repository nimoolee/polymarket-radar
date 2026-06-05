#!/bin/zsh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UID_VALUE="$(id -u)"

if [[ "${1:-}" == "--unload" ]]; then
  launchctl bootout "gui/$UID_VALUE" "$HOME/Library/LaunchAgents/com.polymonitor.frontend.plist" 2>/dev/null || true
  launchctl bootout "gui/$UID_VALUE" "$HOME/Library/LaunchAgents/com.polymonitor.backend.plist" 2>/dev/null || true
  echo "PolyMonitor 后台服务已卸载。需要重新打开页面时运行: $ROOT/scripts/ensure_local_services.sh"
  exit 0
fi

launchctl kickstart -k "gui/$UID_VALUE/com.polymonitor.backend" 2>/dev/null || true
launchctl kickstart -k "gui/$UID_VALUE/com.polymonitor.frontend" 2>/dev/null || true

echo "PolyMonitor 已重启后台服务，未卸载 launchd。"
echo "- 前端: http://127.0.0.1:5173"
echo "- 后端: http://127.0.0.1:8000"
