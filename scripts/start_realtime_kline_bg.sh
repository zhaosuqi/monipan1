#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

if ! command -v conda >/dev/null 2>&1; then
  echo "conda not found; install or adjust PATH" >&2
  exit 1
fi

# Activate bigtree environment
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate bigtree

cd "$ROOT_DIR"
nohup python ./data/realtime_kline_sync.py >> "$LOG_DIR/realtime_kline_sync.log" 2>&1 &
echo $! > "$LOG_DIR/realtime_kline_sync.pid"
echo "realtime_kline_sync started in background. PID=$(cat "$LOG_DIR/realtime_kline_sync.pid")"
