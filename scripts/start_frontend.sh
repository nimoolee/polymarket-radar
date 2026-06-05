#!/bin/zsh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
NODE_BIN="${NODE_BIN:-$(command -v node)}"

cd "$ROOT/frontend"
exec "$NODE_BIN" "$ROOT/frontend/node_modules/vite/bin/vite.js" --host 0.0.0.0 --port 5173
