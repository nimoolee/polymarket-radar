#!/usr/bin/env zsh
set -euo pipefail

REMOTE="${POLY_REMOTE:-}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SSH_CMD="${POLY_SSH_CMD:-ssh}"

if [[ -z "$REMOTE" ]]; then
  echo "请先设置远程目标，例如:"
  echo "POLY_REMOTE=user@host ./scripts/sync_remote.sh"
  exit 1
fi

if [[ -n "${SSHPASS:-}" ]] && command -v sshpass >/dev/null 2>&1; then
  SSH_CMD="sshpass -e $SSH_CMD"
fi

rsync -az \
  -e "$SSH_CMD" \
  --exclude 'backend/.venv' \
  --exclude 'backend/.env' \
  --exclude 'backend/.env.docker' \
  --exclude 'frontend/node_modules' \
  --exclude 'frontend/dist' \
  --exclude 'frontend/.env' \
  --exclude 'frontend/.env.docker' \
  --exclude 'logs' \
  --exclude '.git' \
  --exclude '.DS_Store' \
  "$ROOT_DIR/" "$REMOTE:~/Poly_Codex/"
