#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NODE_BIN="${NODE_BIN:-node}"

cd "$ROOT_DIR/frontend"
"$NODE_BIN" node_modules/vite/bin/vite.js build --mode production

echo "Production frontend built at $ROOT_DIR/frontend/dist"
