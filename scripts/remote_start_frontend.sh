#!/usr/bin/env zsh
set -euo pipefail

export PATH="$HOME/.local/node-v20.19.0-darwin-x64/bin:$PATH"
cd "$HOME/Poly_Codex/frontend"
exec npm run dev -- --host 0.0.0.0 --port 5173
