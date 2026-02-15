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
# 由于 Python 内部已实现日志轮转 (RotatingFileHandler)，
# 此处将 stdout 丢弃以防日志文件无限膨胀，仅保留 stderr 用于捕获崩溃错误
nohup python ./data/sync_macd_indicators.py --loop >/dev/null 2>> "$LOG_DIR/sync_macd_indicators.error.log" &
echo $! > "$LOG_DIR/sync_macd_indicators.pid"
echo "sync_macd_indicators started in background. PID=$(cat "$LOG_DIR/sync_macd_indicators.pid")"
