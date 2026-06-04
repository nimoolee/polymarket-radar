#!/usr/bin/env zsh
set -euo pipefail

cd "$HOME/Poly_Codex/backend"
exec "$HOME/Poly_Codex/backend/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000
