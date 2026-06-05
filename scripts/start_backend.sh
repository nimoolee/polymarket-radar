#!/bin/zsh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT/backend"
exec "$ROOT/backend/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000
