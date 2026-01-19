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

# 如果有 .env 文件，加载它（使用 set -a 自动导出）
if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  source "$ROOT_DIR/.env"
  set +a
fi

# 设置/覆盖关键环境变量
export BINANCE_TESTNET=1
export DB_SIM_MODE=0
export REPLAY_MODE=0
export EXCHANGE_TYPE=binance_testnet

echo "=================================================="
echo "启动数据驱动模拟盘交易系统"
echo "=================================================="
echo "交易所: 币安测试网"
echo "交易对: BTCUSD_PERP"
echo "数据源: klines_1m_macd_smooth_ma 表"
echo "API Key: ${BINANCE_TESTNET_API_KEY:0:8}..."
echo "=================================================="


nohup python ./data/db_driven_trading.py >> "$LOG_DIR/db_driven_trading.log" 2>&1 &
echo $! > "$LOG_DIR/db_driven_trading.pid"
pid=$(cat "$LOG_DIR/db_driven_trading.pid")
echo "db_driven_trading started in background. PID=${pid}"
