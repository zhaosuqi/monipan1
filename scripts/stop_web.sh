#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$LOG_DIR/web.pid"

if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE")
  if ps -p "$PID" > /dev/null 2>&1; then
    echo "Stopping web service (PID: $PID)..."
    kill "$PID"
    rm -f "$PID_FILE"
    echo "Web service stopped."
  else
    echo "Web service is not running (stale PID file)."
    rm -f "$PID_FILE"
  fi
else
  echo "Web service is not running (no PID file)."
fi
