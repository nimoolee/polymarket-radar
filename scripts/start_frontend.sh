#!/bin/zsh
set -e

cd /Users/infinity/Python/Poly_Codex/frontend
exec /opt/homebrew/bin/node /Users/infinity/Python/Poly_Codex/frontend/node_modules/vite/bin/vite.js --host 0.0.0.0 --port 5173
