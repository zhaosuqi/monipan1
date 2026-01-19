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
nohup python ./data/sync_macd_indicators.py --loop >> "$LOG_DIR/sync_macd_indicators.log" 2>&1 &
echo $! > "$LOG_DIR/sync_macd_indicators.pid"
echo "sync_macd_indicators started in background. PID=$(cat "$LOG_DIR/sync_macd_indicators.pid")"
