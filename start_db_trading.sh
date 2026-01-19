#!/bin/bash
# 启动数据驱动模拟盘交易系统
# 使用币安测试网进行交易

cd "$(dirname "$0")"

# 如果有 .env 文件，加载它（使用 set -a 自动导出）
if [ -f ".env" ]; then
    set -a
    source .env
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

# 运行交易系统
python3 data/db_driven_trading.py "$@"
