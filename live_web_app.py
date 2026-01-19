#!/usr/bin/env python3
"""
实时模拟盘Web应用
支持实时K线数据获取和WebSocket推送
"""
import os
from dotenv import load_dotenv

# 必须在导入其他模块之前加载环境变量
load_dotenv()

import time
import threading
from datetime import datetime, timedelta

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import pandas as pd

from exchange_layer.binance_exchange import BinanceExchange
from exchange_layer.exchange_factory import get_exchange, reset_exchange
from trade_module.trade_engine import TradeEngine
from core.logger import get_logger
from core.config import config
from core.database import get_db

logger = get_logger('live_web')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'live-trading-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# 全局变量
exchange = None
trade_engine = None
live_thread = None
stop_event = threading.Event()
klines_buffer = []
latest_kline = None

# 日志缓冲区
log_buffer = []
MAX_LOG_LINES = 100


class LogHandler:
    """自定义日志处理器，捕获日志到缓冲区"""
    def __init__(self):
        self.logger = get_logger('live_web_capture')

    def emit(self, record):
        # 格式化日志
        log_entry = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'level': record.levelname,
            'message': record.getMessage()
        }

        # 添加到缓冲区
        log_buffer.append(log_entry)
        if len(log_buffer) > MAX_LOG_LINES:
            log_buffer.pop(0)

        # 通过WebSocket推送到前端
        try:
            socketio.emit('log_update', log_entry)
        except:
            pass  # WebSocket可能未连接


def get_historical_klines(symbol='BTCUSD_PERP', limit=1000):
    """获取历史K线数据用于预加载"""
    global exchange

    if not exchange:
        return []

    try:
        klines = exchange.get_klines(
            symbol=symbol,
            interval='1m',
            limit=limit
        )

        logger.info(f"已获取 {len(klines)} 条历史K线")
        return klines
    except Exception as e:
        logger.error(f"获取历史K线失败: {e}")
        return []


def kline_to_dict(kline):
    """转换K线对象为字典"""
    return {
        'time': kline.open_time.strftime('%Y-%m-%d %H:%M:%S'),
        'open': float(kline.open),
        'high': float(kline.high),
        'low': float(kline.low),
        'close': float(kline.close),
        'volume': float(kline.volume)
    }


def live_kline_thread():
    """后台线程：获取实时K线数据"""
    global exchange, trade_engine, latest_kline, klines_buffer

    logger.info("实时K线线程启动")

    while not stop_event.is_set():
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

            new_kline = klines[0]

            # 检查是否有新K线
            if latest_kline is None or new_kline.open_time != latest_kline.open_time:
                latest_kline = new_kline

                # 转换为字典
                kline_dict = kline_to_dict(new_kline)

                # 添加到缓冲区
                klines_buffer.append(kline_dict)
                if len(klines_buffer) > 1000:  # 保持最近1000条
                    klines_buffer.pop(0)

                # 推送到前端
                socketio.emit('new_kline', kline_dict)

                logger.info(
                    f"新K线: {kline_dict['time']} | "
                    f"O:{kline_dict['open']:.2f} "
                    f"H:{kline_dict['high']:.2f} "
                    f"L:{kline_dict['low']:.2f} "
                    f"C:{kline_dict['close']:.2f}"
                )

                # 处理交易信号
                if trade_engine:
                    try:
                        kline_data = {
                            'open_time': new_kline.open_time,
                            'open': new_kline.open,
                            'high': new_kline.high,
                            'low': new_kline.low,
                            'close': new_kline.close,
                            'volume': new_kline.volume
                        }

                        trade_engine.process_tick(
                            ts=new_kline.open_time,
                            row=kline_data,
                            signal=None
                        )
                    except Exception as e:
                        logger.error(f"处理交易信号失败: {e}")

            # 等待下一分钟
            time.sleep(60)

        except Exception as e:
            logger.error(f"实时K线线程出错: {e}", exc_info=True)
            time.sleep(30)


# ==================== 路由 ====================

@app.route('/')
def index():
    """主页"""
    return render_template('live_monitor.html')


@app.route('/api/historical-klines')
def api_historical_klines():
    """获取历史K线数据API"""
    limit = request.args.get('limit', 1000, type=int)

    # 从缓冲区返回
    klines = klines_buffer[-limit:] if klines_buffer else []

    # 如果缓冲区为空，尝试从API加载
    if not klines:
        api_klines = get_historical_klines(limit=limit)
        klines = [kline_to_dict(k) for k in api_klines]
        klines_buffer.extend(klines)

    return jsonify({
        'status': 'success',
        'data': klines,
        'count': len(klines)
    })


@app.route('/api/account')
def api_account():
    """获取账户信息"""
    try:
        account = exchange.get_account()
        return jsonify({
            'status': 'success',
            'data': {
                'total_wallet_balance': float(account.total_wallet_balance),
                'available_balance': float(account.available_balance),
                'positions': []
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        })


@app.route('/api/logs')
def api_logs():
    """获取日志"""
    return jsonify({
        'status': 'success',
        'data': log_buffer
    })


@app.route('/api/status')
def api_status():
    """获取运行状态"""
    return jsonify({
        'status': 'success',
        'data': {
            'exchange_connected': exchange.is_connected() if exchange else False,
            'exchange_type': 'binance_testnet',
            'symbol': config.SYMBOL,
            'kline_count': len(klines_buffer),
            'latest_kline_time': latest_kline.open_time.strftime('%Y-%m-%d %H:%M:%S') if latest_kline else None,
            'log_count': len(log_buffer)
        }
    })


# ==================== SocketIO事件 ====================

@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    logger.info(f"客户端已连接: {request.sid}")

    # 发送最新状态
    emit('status_update', {
        'exchange_connected': exchange.is_connected() if exchange else False,
        'symbol': config.SYMBOL
    })

    # 发送最近的日志
    for log_entry in log_buffer[-50:]:
        emit('log_update', log_entry)


@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开"""
    logger.info(f"客户端已断开: {request.sid}")


@socketio.on('request_initial_data')
def handle_request_initial_data():
    """客户端请求初始数据"""
    # 发送历史K线
    klines = klines_buffer[-1000:] if klines_buffer else []
    emit('initial_klines', {'klines': klines})

    # 发送最近日志
    for log_entry in log_buffer[-50:]:
        emit('log_update', log_entry)


# ==================== 主程序 ====================

def main():
    """主程序"""
    global exchange, trade_engine, live_thread

    logger.info("="*80)
    logger.info("启动实时模拟盘Web服务")
    logger.info("="*80)

    # 检查配置
    if config.REPLAY_MODE or config.DB_SIM_MODE:
        logger.error("❌ 当前为回测模式！")
        logger.error("请先运行: ./switch_to_testnet.sh")
        return

    # 检查API密钥
    api_key = os.getenv('BINANCE_API_KEY', '')
    api_secret = os.getenv('BINANCE_API_SECRET', '')

    if not api_key or not api_secret or api_key == 'your_testnet_api_key_here':
        logger.error("❌ 未配置API密钥！")
        logger.error("请在 .env 文件中配置 BINANCE_API_KEY 和 BINANCE_API_SECRET")
        return

    # 创建交易所连接
    exchange = get_exchange()
    if not exchange.connect():
        logger.error("❌ 交易所连接失败！")
        return

    logger.info("✓ 已连接到币安测试网")

    # 创建交易引擎
    trade_engine = TradeEngine()
    logger.info("✓ 交易引擎已创建")

    # 预加载历史数据
    logger.info("预加载历史K线数据...")
    historical_klines = get_historical_klines(limit=1000)

    if historical_klines:
        for kline in historical_klines:
            klines_buffer.append(kline_to_dict(kline))
        logger.info(f"✓ 已加载 {len(klines_buffer)} 条历史K线")
    else:
        logger.warning("⚠️  未获取到历史K线")

    # 启动实时K线线程
    stop_event.clear()
    live_thread = threading.Thread(target=live_kline_thread, daemon=True)
    live_thread.start()
    logger.info("✓ 实时K线线程已启动")

    # 输出访问信息
    PORT = 5001
    logger.info(f"访问地址: http://localhost:{PORT}")
    logger.info(f"监控页面: http://localhost:{PORT}/")
    logger.info("="*80)
    logger.info("按 Ctrl+C 停止服务")
    logger.info("="*80)

    try:
        # 运行Flask-SocketIO
        socketio.run(
            app,
            host='0.0.0.0',
            port=PORT,
            debug=False,
            allow_unsafe_werkzeug=True
        )
    except KeyboardInterrupt:
        logger.info("\n收到退出信号")
    finally:
        # 清理
        stop_event.set()
        reset_exchange()
        logger.info("服务已停止")


if __name__ == '__main__':
    main()
