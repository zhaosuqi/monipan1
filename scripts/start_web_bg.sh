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

# 读取端口配置（优先级：环境变量 > .env文件 > 默认值）
# 1. 首先检查 WEB_PORT 环境变量
if [ -n "${WEB_PORT:-}" ]; then
  PORT="$WEB_PORT"
  echo "Using WEB_PORT from environment: $PORT"
else
  # 2. 尝试从 .env 文件读取
  if [ -f "$ROOT_DIR/.env" ]; then
    ENV_PORT=$(grep -E '^WEB_PORT=' "$ROOT_DIR/.env" | cut -d'=' -f2 | tr -d ' ')
    if [ -n "$ENV_PORT" ]; then
      PORT="$ENV_PORT"
      echo "Using WEB_PORT from .env: $PORT"
    else
      PORT="8076"
      echo "WEB_PORT not found in .env, using default: $PORT"
    fi
  else
    PORT="8076"
    echo ".env not found, using default port: $PORT"
  fi
fi

# 检查端口是否已被占用
if lsof -i :"$PORT" >/dev/null 2>&1; then
  echo "Warning: Port $PORT is already in use!" >&2
  exit 1
fi

# 启动 web 服务
# stdout 和 stderr 都记录到日志文件
nohup python ./web/kline_viewer.py --port "$PORT" >> "$LOG_DIR/web.log" 2>&1 &
echo $! > "$LOG_DIR/web.pid"
echo "Web service started in background. PID=$(cat "$LOG_DIR/web.pid"), PORT=$PORT"
echo "Access: http://localhost:$PORT"
