#!/bin/zsh
set -e

cd /Users/infinity/Python/Poly_Codex/backend
exec /Users/infinity/Python/Poly_Codex/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
