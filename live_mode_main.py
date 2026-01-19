#!/usr/bin/env python3
"""
实时模拟盘主程序
从币安测试网获取实时K线，驱动交易决策
"""
import os
import time
from datetime import datetime
from dotenv import load_dotenv

from exchange_layer.binance_exchange import BinanceExchange
from exchange_layer.exchange_factory import get_exchange, reset_exchange
from trade_module.trade_engine import TradeEngine
from core.logger import get_logger
from core.config import config

logger = get_logger('live_mode')

# 加载环境变量
load_dotenv()

def live_trading_loop():
    """实时交易循环"""
    logger.info("="*80)
    logger.info("启动实时模拟盘模式")
    logger.info("="*80)

    # 检查配置
    if config.REPLAY_MODE or config.DB_SIM_MODE:
        logger.error("❌ 当前为回测模式！请先切换到实时模式")
        logger.error("运行: ./switch_to_testnet.sh")
        return False

    # 创建交易所实例
    exchange = get_exchange()
    if not exchange.is_connected():
        logger.error("❌ 交易所未连接！")
        return False

    logger.info("✓ 已连接到交易所")

    # 创建交易引擎
    trade_engine = TradeEngine(exchange=exchange)

    # 预加载最新K线（用于MACD计算）
    logger.info("预加载最近K线数据...")
    try:
        recent_klines = exchange.get_klines(
            symbol=config.SYMBOL,
            interval='1m',
            limit=1000
        )
        logger.info(f"✓ 已加载最近 {len(recent_klines)} 条K线")
    except Exception as e:
        logger.error(f"❌ 加载K线失败: {e}")
        return False

    logger.info("="*80)
    logger.info("开始实时交易循环")
    logger.info("="*80)

    # 记录上次处理的K线时间
    last_kline_time = None

    try:
        while True:
            try:
                # 获取最新K线
                klines = exchange.get_klines(
                    symbol=config.SYMBOL,
                    interval='1m',
                    limit=1
                )

                if not klines:
                    logger.warning("未获取到K线数据")
                    time.sleep(10)
                    continue

                latest_kline = klines[0]

                # 检查是否有新K线
                if last_kline_time and latest_kline.open_time == last_kline_time:
                    # 没有新K线，等待
                    time.sleep(5)
                    continue

                # 有新K线
                last_kline_time = latest_kline.open_time
                logger.info("")
                logger.info("="*80)
                logger.info(f"新K线: {latest_kline.open_time}")
                logger.info(f"  开: {latest_kline.open:.2f}")
                logger.info(f"  高: {latest_kline.high:.2f}")
                logger.info(f"  低: {latest_kline.low:.2f}")
                logger.info(f"  收: {latest_kline.close:.2f}")
                logger.info("="*80)

                # 构造K线数据字典
                kline_dict = {
                    'open_time': latest_kline.open_time,
                    'open': latest_kline.open,
                    'high': latest_kline.high,
                    'low': latest_kline.low,
                    'close': latest_kline.close,
                    'volume': latest_kline.volume,
                    'close_time': latest_kline.close_time
                }

                # 处理K线（信号判断、订单检查等）
                trade_engine.process_tick(
                    ts=latest_kline.open_time,
                    row=kline_dict,
                    signal=None  # 信号由trade_engine内部计算
                )

                # 检查订单状态
                if trade_engine.positions:
                    logger.info(f"当前持仓数: {len(trade_engine.positions)}")
                    for pos in trade_engine.positions:
                        logger.info(f"  {pos.side}: {pos.contracts}张 @ {pos.entry_price:.2f}")

                # 等待下一分钟
                logger.info("等待下一分钟...")
                time.sleep(60)

            except KeyboardInterrupt:
                logger.info("\n收到退出信号")
                break

            except Exception as e:
                logger.error(f"处理K线时出错: {e}", exc_info=True)
                time.sleep(30)  # 出错后等待30秒再继续

    finally:
        # 清理
        logger.info("停止实时交易")
        reset_exchange()

    return True

if __name__ == '__main__':
    try:
        live_trading_loop()
    except Exception as e:
        logger.error(f"程序异常退出: {e}", exc_info=True)
