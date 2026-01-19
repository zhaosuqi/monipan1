#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v fswatch >/dev/null 2>&1; then
  echo "fswatch not found. Install it via: brew install fswatch" >&2
  exit 1
fi

echo "Starting auto-commit watcher in $ROOT_DIR"
echo "Press Ctrl+C to stop"

fswatch -or . \
  --exclude "\.git" \
  --exclude "data/logs" \
  --exclude "logs" \
  --exclude "__pycache__" \
  --exclude "\.vscode" \
  --exclude "\.idea" |
while read -r _; do
  if git status --porcelain | grep -q .; then
    ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    git add -A
    git commit -m "auto-commit ${ts}" || true
    echo "Committed changes at ${ts}"
  fi
done
