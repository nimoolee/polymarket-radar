#!/bin/zsh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
NODE_BIN="${NODE_BIN:-}"

if [[ -z "$NODE_BIN" ]]; then
  for candidate in /opt/homebrew/bin/node /usr/local/bin/node /usr/bin/node; do
    if [[ -x "$candidate" ]]; then
      NODE_BIN="$candidate"
      break
    fi
  done
fi

if [[ -z "$NODE_BIN" ]]; then
  NODE_BIN="$(PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" command -v node || true)"
fi

if [[ -z "$NODE_BIN" ]]; then
  echo "Node.js not found. Install Node.js or set NODE_BIN before launching frontend." >&2
  exit 1
fi

cd "$ROOT/frontend"
exec "$NODE_BIN" "$ROOT/frontend/node_modules/vite/bin/vite.js" --host 0.0.0.0 --port 5173
