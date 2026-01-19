#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web应用 - 配置和监控系统
提供三个主要页面:
1. 配置页面 - 模式切换和连接参数维护
2. 运行状态监控页面 - K线图、订单监控、参数展示
3. 参数维护页面 - 参数展示和JSON导入

支持三种模式:
- backtest: 数据库回测模式
- simulation: 模拟盘模式（币安测试网）
- live: 实盘模式（币安实盘）
"""

import json
import os
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit

from dotenv import load_dotenv

# 必须在导入其他模块之前加载环境变量
load_dotenv()

from core.config import config
from core.logger import get_logger

logger = get_logger(__name__)

# 创建Flask应用
app = Flask(__name__,
            template_folder='web/templates',
            static_folder='web/static')
app.config['SECRET_KEY'] = 'monipan-secret-key-2026'

# 创建SocketIO实例
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 全局状态（模式将在启动时动态获取）
bot_state = {
    'running': False,
    'mode': None,  # 将在第一次访问时动态获取
    'start_time': None,
    'connected': False
}

# 模拟盘/实盘模式的实时数据和线程
# 注意：模拟盘模式下，K线数据从实盘获取，订单操作用测试网
live_data = {
    'kline_exchange': None,  # K线数据交易所（总是用实盘）
    'order_exchange': None,  # 订单操作交易所（模拟盘用测试网，实盘用实盘）
    'trade_engine': None,
    'klines_buffer': [],
    'thread': None,
    'stop_event': threading.Event(),
    'latest_kline': None
}


# ==================== 路由 ====================

@app.route('/')
def index():
    """首页 - 重定向到配置页面"""
    return render_template('index.html')


@app.route('/config')
def config_page():
    """配置页面"""
    return render_template('config.html',
                         current_mode=get_current_mode(),
                         config=get_config_dict())


@app.route('/monitor')
def monitor_page():
    """运行状态监控页面"""
    return render_template('monitor.html',
                         bot_state=bot_state,
                         config=get_config_dict())


@app.route('/parameters')
def parameters_page():
    """参数维护页面"""
    return render_template('parameters.html',
                         config=get_config_dict())


# ==================== API接口 ====================

@app.route('/api/config', methods=['GET'])
def get_config():
    """获取当前配置"""
    return jsonify({
        'success': True,
        'data': get_config_dict()
    })


@app.route('/api/config/mode', methods=['GET'])
def get_mode():
    """获取当前模式"""
    return jsonify({
        'success': True,
        'data': {
            'mode': get_current_mode(),
            'mode_name': get_mode_name(get_current_mode())
        }
    })


@app.route('/api/config/mode', methods=['POST'])
def set_mode():
    """设置运行模式"""
    try:
        data = request.json
        mode = data.get('mode')

        if mode not in ['live', 'simulation', 'backtest']:
            return jsonify({
                'success': False,
                'message': '无效的模式'
            })

        # 保存到环境变量
        if mode == 'live':
            os.environ['DB_SIM_MODE'] = '0'
            os.environ['REPLAY_MODE'] = '0'
            os.environ['BINANCE_TESTNET'] = '0'
            # 更新config对象
            config.DB_SIM_MODE = False
            config.REPLAY_MODE = False
            config.BINANCE_TESTNET = False
        elif mode == 'simulation':
            os.environ['DB_SIM_MODE'] = '0'
            os.environ['REPLAY_MODE'] = '0'
            os.environ['BINANCE_TESTNET'] = '1'
            # 更新config对象
            config.DB_SIM_MODE = False
            config.REPLAY_MODE = False
            config.BINANCE_TESTNET = True
        elif mode == 'backtest':
            os.environ['DB_SIM_MODE'] = '1'
            os.environ['REPLAY_MODE'] = '1'
            os.environ['BINANCE_TESTNET'] = '0'
            # 更新config对象
            config.DB_SIM_MODE = True
            config.REPLAY_MODE = True
            config.BINANCE_TESTNET = False

        logger.info(f"模式已切换为: {get_mode_name(mode)}")

        # 重置数据源单例，使其使用新的配置
        from data_module.data_source_adapter import reset_data_source
        reset_data_source()

        return jsonify({
            'success': True,
            'message': f'模式已切换为: {get_mode_name(mode)}',
            'data': {'mode': mode}
        })

    except Exception as e:
        logger.error(f"设置模式失败: {e}")
        return jsonify({
            'success': False,
            'message': f'设置模式失败: {str(e)}'
        })


@app.route('/api/config/binance', methods=['POST'])
def set_binance_config():
    """设置Binance连接参数"""
    try:
        data = request.json

        # 更新配置
        config.BINANCE_API_KEY = data.get('api_key', '')
        config.BINANCE_API_SECRET = data.get('api_secret', '')
        config.BINANCE_TESTNET = data.get('testnet', False)
        config.SYMBOL = data.get('symbol', 'BTCUSD_PERP')

        logger.info("Binance配置已更新")

        return jsonify({
            'success': True,
            'message': 'Binance配置已更新'
        })

    except Exception as e:
        logger.error(f"设置Binance配置失败: {e}")
        return jsonify({
            'success': False,
            'message': f'设置失败: {str(e)}'
        })


@app.route('/api/parameters', methods=['GET'])
def get_parameters():
    """获取所有参数"""
    try:
        params = get_config_dict()

        # 格式化参数列表
        param_list = []
        for key, value in params.items():
            param_list.append({
                'key': key,
                'value': value,
                'type': type(value).__name__
            })

        return jsonify({
            'success': True,
            'data': param_list
        })

    except Exception as e:
        logger.error(f"获取参数失败: {e}")
        return jsonify({
            'success': False,
            'message': f'获取参数失败: {str(e)}'
        })


@app.route('/api/parameters', methods=['POST'])
def update_parameters():
    """更新参数"""
    try:
        data = request.json
        key = data.get('key')
        value = data.get('value')

        if not key:
            return jsonify({
                'success': False,
                'message': '参数名不能为空'
            })

        # 检查是否正在运行
        if bot_state['running']:
            return jsonify({
                'success': False,
                'message': '任务运行中，无法修改参数'
            })

        # 更新配置
        setattr(config, key, value)

        logger.info(f"参数已更新: {key} = {value}")

        return jsonify({
            'success': True,
            'message': f'参数 {key} 已更新'
        })

    except Exception as e:
        logger.error(f"更新参数失败: {e}")
        return jsonify({
            'success': False,
            'message': f'更新失败: {str(e)}'
        })


@app.route('/api/parameters/import', methods=['POST'])
def import_parameters():
    """导入JSON参数"""
    try:
        # 检查是否正在运行
        if bot_state['running']:
            return jsonify({
                'success': False,
                'message': '任务运行中，无法导入参数'
            })

        data = request.json
        params = data.get('parameters')

        if not params:
            return jsonify({
                'success': False,
                'message': '参数不能为空'
            })

        # 批量更新配置
        updated_count = 0
        for key, value in params.items():
            if hasattr(config, key):
                setattr(config, key, value)
                updated_count += 1

        logger.info(f"已导入 {updated_count} 个参数")

        return jsonify({
            'success': True,
            'message': f'成功导入 {updated_count} 个参数',
            'data': {'updated_count': updated_count}
        })

    except Exception as e:
        logger.error(f"导入参数失败: {e}")
        return jsonify({
            'success': False,
            'message': f'导入失败: {str(e)}'
        })


@app.route('/api/parameters/export', methods=['GET'])
def export_parameters():
    """导出JSON参数"""
    try:
        params = get_config_dict()

        return jsonify({
            'success': True,
            'data': params
        })

    except Exception as e:
        logger.error(f"导出参数失败: {e}")
        return jsonify({
            'success': False,
            'message': f'导出失败: {str(e)}'
        })


@app.route('/api/bot/start', methods=['POST'])
def start_bot():
    """启动交易机器人"""
    try:
        if bot_state['running']:
            return jsonify({
                'success': False,
                'message': '机器人已在运行中'
            })

        current_mode = get_current_mode()

        # 根据模式启动不同的机器人
        if current_mode == 'backtest':
            # 数据库回测模式 - 在后台线程运行
            import threading

            bot_state['running'] = True
            bot_state['mode'] = current_mode
            bot_state['start_time'] = None
            bot_state['connected'] = False

            # 添加回测时间范围信息
            bot_state['backtest_start'] = config.REPLAY_START
            bot_state['backtest_end'] = config.REPLAY_END

            # 创建后台线程运行回测
            backtest_thread = threading.Thread(target=run_backtest_worker, daemon=True)
            backtest_thread.start()

            logger.info(f"回测机器人已启动 - 模式: {get_mode_name(current_mode)}")
            logger.info(f"回测时间范围: {config.REPLAY_START} ~ {config.REPLAY_END}")

        elif current_mode in ['live', 'simulation']:
            # 实盘或模拟盘模式 - 启动实时交易
            import threading

            bot_state['running'] = True
            bot_state['mode'] = current_mode
            bot_state['start_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            bot_state['connected'] = False

            # 启动实时交易线程
            live_thread = threading.Thread(target=run_live_trading_worker, daemon=True)
            live_thread.start()

            logger.info(f"实时交易机器人已启动 - 模式: {get_mode_name(current_mode)}")
            logger.info(f"交易对: {config.SYMBOL}")
            logger.info(f"交易所: {'币安测试网' if config.BINANCE_TESTNET else '币安实盘'}")

        # 通知所有客户端
        socketio.emit('bot_state_changed', bot_state)

        return jsonify({
            'success': True,
            'message': f'机器人已启动 - {get_mode_name(current_mode)}',
            'data': bot_state
        })

    except Exception as e:
        logger.error(f"启动机器人失败: {e}")
        return jsonify({
            'success': False,
            'message': f'启动失败: {str(e)}'
        })


@app.route('/api/bot/stop', methods=['POST'])
def stop_bot():
    """停止交易机器人"""
    try:
        if not bot_state['running']:
            return jsonify({
                'success': False,
                'message': '机器人未运行'
            })

        # 如果是模拟盘/实盘模式，停止实时交易线程
        if bot_state['mode'] in ['simulation', 'live']:
            live_data['stop_event'].set()
            logger.info("已发送停止信号到实时交易线程")

        bot_state['running'] = False
        bot_state['connected'] = False

        logger.info("交易机器人已停止")

        # 通知所有客户端
        socketio.emit('bot_state_changed', bot_state)

        return jsonify({
            'success': True,
            'message': '交易机器人已停止',
            'data': bot_state
        })

    except Exception as e:
        logger.error(f"停止机器人失败: {e}")
        return jsonify({
            'success': False,
            'message': f'停止失败: {str(e)}'
        })


@app.route('/api/bot/state', methods=['GET'])
def get_bot_state():
    """获取机器人状态"""
    # 动态获取当前模式
    current_mode = get_current_mode()

    # 如果机器人未运行，使用当前配置的模式
    # 如果机器人正在运行，使用启动时设置的模式
    state_to_return = bot_state.copy()
    if not state_to_return['running']:
        state_to_return['mode'] = current_mode

    return jsonify({
        'success': True,
        'data': state_to_return
    })


@app.route('/api/klines', methods=['GET'])
def get_klines():
    """获取K线数据"""
    try:
        limit = request.args.get('limit', 100, type=int)
        start_time = request.args.get('start_time', None)
        end_time = request.args.get('end_time', None)

        current_mode = get_current_mode()
        logger.info(f"获取K线数据请求, mode={current_mode}, limit={limit}")

        # 根据模式选择数据源
        if current_mode in ['simulation', 'live']:
            # 模拟盘/实盘模式 - 从交易所获取或使用缓冲区数据
            klines = []

            # 优先从缓冲区获取
            if live_data['klines_buffer']:
                klines = live_data['klines_buffer'][-limit:]
                logger.info(f"从缓冲区获取 {len(klines)} 条K线")
            else:
                # 缓冲区为空，尝试从交易所获取
                if live_data['kline_exchange']:
                    try:
                        api_klines = live_data['kline_exchange'].get_klines(
                            symbol=config.SYMBOL,
                            interval='1m',
                            limit=limit
                        )
                        klines = api_klines
                        logger.info(f"从交易所API获取 {len(klines)} 条K线")
                    except Exception as e:
                        logger.error(f"从交易所获取K线失败: {e}")
                        return jsonify({
                            'success': False,
                            'message': f'无法获取K线数据: {str(e)}'
                        })

            # 格式化K线数据
            formatted_klines = []
            for kline in klines:
                formatted_klines.append({
                    'time': kline.open_time.strftime('%Y-%m-%d %H:%M:%S') if hasattr(kline.open_time, 'strftime') else str(kline.open_time),
                    'open': float(kline.open),
                    'high': float(kline.high),
                    'low': float(kline.low),
                    'close': float(kline.close),
                    'volume': float(kline.volume)
                })

            return jsonify({
                'success': True,
                'data': formatted_klines
            })

        else:  # backtest mode
            # 回测模式 - 从数据库读取
            from data_module.db_kline_reader import DbKlineReader

            # 使用包含MACD指标的表
            table_name = 'klines_1m_macd_smooth_ma'
            logger.info(f"从表 {table_name} 读取数据")

            reader = DbKlineReader(
                db_path=config.HIST_DB_PATH,
                table_name=table_name
            )

            # 如果指定了时间范围,使用时间范围查询
            if start_time and end_time:
                klines = reader.get_klines_by_time_range(
                    start_time=start_time,
                    end_time=end_time
                )
                logger.info(f"按时间范围获取到 {len(klines)} 条K线数据")
            elif start_time:
                # 只有开始时间,获取从该时间开始的limit条
                klines = reader.get_klines_by_time_range(
                    start_time=start_time,
                    end_time=None
                )
                # 限制数量
                if len(klines) > limit:
                    klines = klines[:limit]
                logger.info(f"从{start_time}开始获取到 {len(klines)} 条K线数据")
            else:
                # 默认获取最新的limit条
                klines = reader.get_klines(limit=limit)
                logger.info(f"获取到 {len(klines)} 条K线数据")

            # 格式化K线数据
            formatted_klines = []
            for kline in klines:
                formatted_klines.append({
                    'time': kline.get('open_time') or kline.get('close_time'),
                    'open': float(kline.get('open', 0)),
                    'high': float(kline.get('high', 0)),
                    'low': float(kline.get('low', 0)),
                    'close': float(kline.get('close', 0)),
                    'volume': float(kline.get('volume', 0))
                })

            logger.info(f"格式化完成, 返回 {len(formatted_klines)} 条数据")

            return jsonify({
                'success': True,
                'data': formatted_klines
            })

    except Exception as e:
        logger.error(f"获取K线数据失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'获取失败: {str(e)}'
        })


@app.route('/api/markers', methods=['GET'])
def get_markers():
    """获取交易标记(从sim_log表读取,用于K线图显示)"""
    try:
        import sqlite3

        conn = sqlite3.connect(
            config.DB_PATH,
            timeout=30.0,
            isolation_level=None
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 获取所有交易日志
        cursor.execute("""
            SELECT log_time, event, side, price, contracts, pnl
            FROM sim_log
            ORDER BY log_time ASC
            LIMIT 500
        """)
        rows = cursor.fetchall()
        conn.close()

        markers = []
        for row in rows:
            try:
                # 将sqlite3.Row对象转换为字典
                row_dict = dict(row)

                # 判断标记类型和颜色
                event = row_dict.get('event', '')
                side = row_dict.get('side', '')
                price = float(row_dict.get('price', 0))
                timestamp = row_dict.get('log_time', '')

                # 根据事件类型确定标记
                marker_type = 'close'
                color = '#999999'
                shape = 'circle'

                if '开仓' in event:
                    marker_type = 'buy' if side == 'long' else 'sell'
                    color = '#26a69a' if side == 'long' else '#ef5350'
                    shape = 'arrowUp' if side == 'long' else 'arrowDown'
                elif 'TP' in event or '止盈' in event:
                    marker_type = 'close'
                    color = '#26a69a'  # 绿色表示止盈
                    shape = 'circle'
                elif 'STOP' in event or '止损' in event:
                    marker_type = 'close'
                    color = '#ef5350'  # 红色表示止损
                    shape = 'circle'
                elif 'CLOSE_RETREAT' in event or '回撤' in event:
                    marker_type = 'close'
                    color = '#ff9800'  # 橙色表示回撤
                    shape = 'circle'
                elif 'EOD_CLOSE' in event or '超时' in event:
                    marker_type = 'close'
                    color = '#9e9e9e'  # 灰色表示超时
                    shape = 'circle'

                # 转换时间戳为Unix时间戳(秒)
                from datetime import datetime
                try:
                    dt = datetime.fromisoformat(timestamp.replace('+00:00', ''))
                    time = int(dt.timestamp())
                except:
                    # 如果转换失败,尝试其他格式
                    try:
                        dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                        time = int(dt.timestamp())
                    except:
                        continue

                markers.append({
                    'time': time,
                    'position': 'belowBar' if marker_type == 'buy' else 'aboveBar',
                    'color': color,
                    'shape': shape,
                    'size': 2,
                    'text': f"{event} @ {price:.2f}",
                    'event': event,
                    'side': side,
                    'price': price,
                    'pnl': float(row_dict.get('pnl', 0))
                })
            except Exception as e:
                logger.warning(f"处理标记行时出错: {e}")
                continue

        logger.info(f"✓ 从sim_log加载{len(markers)}个交易标记")
        return jsonify({
            'success': True,
            'data': markers
        })

    except Exception as e:
        logger.error(f"获取标记失败: {e}")
        return jsonify({
            'success': False,
            'message': f'获取失败: {str(e)}'
        })


@app.route('/api/orders', methods=['GET'])
def get_orders():
    """获取订单列表"""
    try:
        # 使用独立的SQLite连接，避免跨线程问题
        import sqlite3

        conn = sqlite3.connect(
            config.DB_PATH,
            timeout=30.0,
            isolation_level=None
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 获取模拟订单
        cursor.execute("""
            SELECT id, log_time, event, side, price, contracts, details
            FROM sim_log
            ORDER BY log_time DESC
            LIMIT 100
        """)
        rows = cursor.fetchall()
        conn.close()

        orders = []
        for row in rows:
            try:
                # 将sqlite3.Row对象转换为字典
                row_dict = dict(row)
                orders.append({
                    'id': row_dict.get('id'),
                    'timestamp': row_dict.get('log_time'),
                    'event': row_dict.get('event', ''),
                    'side': row_dict.get('side', ''),
                    'price': float(row_dict.get('price', 0)) if row_dict.get('price') else 0.0,
                    'quantity': float(row_dict.get('contracts', 0)) if row_dict.get('contracts') else 0.0,
                    'pnl': float(row_dict.get('pnl', 0)) if row_dict.get('pnl') is not None else 0.0,
                    'details': row_dict.get('details', ''),
                    'fee_rate': float(row_dict.get('fee_rate', 0)) if row_dict.get('fee_rate') else 0.0,
                    'fee_usd': float(row_dict.get('fee_usd', 0)) if row_dict.get('fee_usd') else 0.0,
                    'trace_id': row_dict.get('trace_id', ''),
                    'realized_pnl': float(row_dict.get('realized_pnl', 0)) if row_dict.get('realized_pnl') is not None else 0.0,
                    'status': row_dict.get('event', '')
                })
            except Exception as e:
                logger.warning(f"处理订单行时出错: {e}, 行数据: {dict(row)}")
                continue

        return jsonify({
            'success': True,
            'data': orders
        })

    except Exception as e:
        logger.error(f"获取订单失败: {e}")
        return jsonify({
            'success': False,
            'message': f'获取失败: {str(e)}'
        })


@app.route('/api/config/update', methods=['POST'])
def update_config():
    """更新配置参数"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'message': '请提供要更新的参数'
            })

        updated_params = []
        errors = []

        # 遍历所有要更新的参数
        for key, value in data.items():
            try:
                # 检查配置对象是否有该属性
                if not hasattr(config, key):
                    errors.append(f'{key}: 参数不存在')
                    continue

                # 获取当前值的类型
                current_value = getattr(config, key)
                current_type = type(current_value)

                # 类型转换
                if current_type == bool:
                    # 处理布尔值
                    if isinstance(value, str):
                        converted_value = value.lower() in ('1', 'true', 'yes', 'on')
                    elif isinstance(value, bool):
                        converted_value = value
                    else:
                        converted_value = bool(value)
                elif current_type == int:
                    converted_value = int(value)
                elif current_type == float:
                    converted_value = float(value)
                elif current_type == list:
                    if isinstance(value, str):
                        import json
                        converted_value = json.loads(value)
                    else:
                        converted_value = list(value)
                else:
                    # 字符串或其他类型
                    converted_value = str(value)

                # 更新配置值
                setattr(config, key, converted_value)
                updated_params.append(f'{key}={converted_value}')

                logger.info(f"配置参数已更新: {key}={converted_value}")

            except (ValueError, TypeError) as e:
                errors.append(f'{key}: 类型转换失败 - {str(e)}')
                logger.error(f"参数 {key} 更新失败: {e}")
            except Exception as e:
                errors.append(f'{key}: {str(e)}')
                logger.error(f"参数 {key} 更新失败: {e}")

        # 返回结果
        if updated_params:
            message = f'已更新 {len(updated_params)} 个参数'
            if errors:
                message += f'，{len(errors)} 个失败'

            return jsonify({
                'success': True,
                'message': message,
                'data': {
                    'updated': updated_params,
                    'errors': errors
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': '没有参数被更新',
                'data': {
                    'errors': errors
                }
            })

    except Exception as e:
        logger.error(f"更新配置失败: {e}")
        return jsonify({
            'success': False,
            'message': f'更新失败: {str(e)}'
        })


@app.route('/api/config/reload', methods=['POST'])
def reload_config():
    """重新加载配置"""
    try:
        config.reload()
        logger.info("配置已重新加载")

        return jsonify({
            'success': True,
            'message': '配置已重新加载'
        })

    except Exception as e:
        logger.error(f"重新加载配置失败: {e}")
        return jsonify({
            'success': False,
            'message': f'重新加载失败: {str(e)}'
        })


@app.route('/api/backtest/session', methods=['POST'])
def start_session_backtest():
    """启动会话模式回测"""
    try:
        if bot_state['running']:
            return jsonify({
                'success': False,
                'message': '机器人已在运行中'
            })

        data = request.json
        split_mode = data.get('split_mode', 'day')  # day, week, month, custom

        # 数据库回测模式 - 在后台线程运行
        import threading
        bot_state['running'] = True
        bot_state['mode'] = 'backtest'
        bot_state['start_time'] = None
        bot_state['connected'] = False

        # 创建后台线程运行会话模式回测
        backtest_thread = threading.Thread(
            target=run_session_backtest_worker,
            args=(split_mode,),
            daemon=True
        )
        backtest_thread.start()

        logger.info(f"会话模式回测已启动 - 划分模式: {split_mode}")

        # 通知所有客户端
        socketio.emit('bot_state_changed', bot_state)

        return jsonify({
            'success': True,
            'message': f'会话模式回测已启动 - {split_mode}',
            'data': bot_state
        })

    except Exception as e:
        logger.error(f"启动会话模式回测失败: {e}")
        return jsonify({
            'success': False,
            'message': f'启动失败: {str(e)}'
        })


# ==================== WebSocket事件 ====================

@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    logger.info(f"客户端已连接: {request.sid}")
    emit('bot_state_changed', bot_state)


@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开"""
    logger.info(f"客户端已断开: {request.sid}")


@socketio.on('subscribe_klines')
def handle_subscribe_klines():
    """订阅K线数据"""
    logger.info(f"客户端订阅K线数据: {request.sid}")
    # 这里可以开始推送K线数据


# ==================== 辅助函数 ====================

def get_current_mode():
    """获取当前模式"""
    if config.DB_SIM_MODE or config.REPLAY_MODE:
        return 'backtest'
    elif config.BINANCE_TESTNET:
        return 'simulation'
    else:
        return 'live'


def get_mode_name(mode):
    """获取模式名称"""
    mode_names = {
        'live': '实盘模式',
        'simulation': '模拟盘模式',
        'backtest': '数据库回测模式'
    }
    return mode_names.get(mode, '未知模式')


def get_config_dict():
    """获取配置字典"""
    return {
        # 模式配置
        'DB_SIM_MODE': config.DB_SIM_MODE,
        'REPLAY_MODE': config.REPLAY_MODE,
        'REPLAY_START': config.REPLAY_START,
        'REPLAY_END': config.REPLAY_END,
        'REPLAY_WARM_DAYS': config.REPLAY_WARM_DAYS,

        # Binance配置
        'BINANCE_API_KEY': config.BINANCE_API_KEY,
        'BINANCE_API_SECRET': '***' if config.BINANCE_API_SECRET else '',
        'BINANCE_TESTNET': config.BINANCE_TESTNET,
        'SYMBOL': config.SYMBOL,

        # 交易配置
        'POSITION_BTC': config.POSITION_BTC,
        'CONTRACT_NOTIONAL': config.CONTRACT_NOTIONAL,

        # 指标配置
        'MACD_FAST': config.MACD_FAST,
        'MACD_SLOW': config.MACD_SLOW,
        'MACD_SIGNAL': config.MACD_SIGNAL,

        # V5 T0参数 - 15分钟
        'T0_HIST15_LIMIT': config.T0_HIST15_LIMIT,
        'T0_HIST15_LIMIT_MIN': config.T0_HIST15_LIMIT_MIN,
        'T0_DIF15_LIMIT': config.T0_DIF15_LIMIT,
        'T0_DIF15_LIMIT_MIN': config.T0_DIF15_LIMIT_MIN,

        # V5 T0参数 - 1小时
        'T0_HIST1H_LIMIT': config.T0_HIST1H_LIMIT,
        'T0_HIST1H_LIMIT_MIN': config.T0_HIST1H_LIMIT_MIN,
        'T0_DIF1H_LIMIT': config.T0_DIF1H_LIMIT,
        'T0_DIF1H_LIMIT_MIN': config.T0_DIF1H_LIMIT_MIN,

        # V5 T0参数 - 4小时
        'T0_HIST4_LIMIT': config.T0_HIST4_LIMIT,
        'T0_HIST4_LIMIT_MIN': config.T0_HIST4_LIMIT_MIN,
        'T0_DIF4_LIMIT': config.T0_DIF4_LIMIT,
        'T0_DIF4_LIMIT_MIN': config.T0_DIF4_LIMIT_MIN,

        # V5 T0参数 - 1天
        'T0_HIST1D_LIMIT': config.T0_HIST1D_LIMIT,
        'T0_HIST1D_LIMIT_MIN': config.T0_HIST1D_LIMIT_MIN,
        'T0_DIF1D_LIMIT': config.T0_DIF1D_LIMIT,
        'T0_DIF1D_LIMIT_MIN': config.T0_DIF1D_LIMIT_MIN,

        # V5 T0参数 - J指标（多）
        'T0_J15M_LIMIT': config.T0_J15M_LIMIT,
        'T0_J1H_LIMIT': config.T0_J1H_LIMIT,
        'T0_J4H_LIMIT': config.T0_J4H_LIMIT,

        # V5 T0参数 - J指标（空）
        'T0_J15M_LIMIT_KONG': config.T0_J15M_LIMIT_KONG,
        'T0_J1H_LIMIT_KONG': config.T0_J1H_LIMIT_KONG,
        'T0_J4H_LIMIT_KONG': config.T0_J4H_LIMIT_KONG,

        # V5 均值参数 - 第一组 (15分钟)
        'MEANS_HIST15_COUNT': config.MEANS_HIST15_COUNT,
        'HIST15_MEANS_LIMIT': config.HIST15_MEANS_LIMIT,
        'MEANS_DIF15_COUNT': config.MEANS_DIF15_COUNT,
        'DIF15_MEANS_LIMIT': config.DIF15_MEANS_LIMIT,
        'MEANS_DEA15_COUNT': config.MEANS_DEA15_COUNT,
        'DEA15_MEANS_LIMIT': config.DEA15_MEANS_LIMIT,

        # V5 均值参数 - 第一组 (1小时)
        'MEANS_HIST1H_COUNT': config.MEANS_HIST1H_COUNT,
        'HIST1H_MEANS_LIMIT': config.HIST1H_MEANS_LIMIT,
        'MEANS_DIF1H_COUNT': config.MEANS_DIF1H_COUNT,
        'DIF1H_MEANS_LIMIT': config.DIF1H_MEANS_LIMIT,
        'MEANS_DEA1H_COUNT': config.MEANS_DEA1H_COUNT,
        'DEA1H_MEANS_LIMIT': config.DEA1H_MEANS_LIMIT,

        # V5 均值参数 - 第一组 (4小时)
        'MEANS_HIST4_COUNT': config.MEANS_HIST4_COUNT,
        'HIST4_MEANS_LIMIT': config.HIST4_MEANS_LIMIT,
        'MEANS_DIF4_COUNT': config.MEANS_DIF4_COUNT,
        'DIF4_MEANS_LIMIT': config.DIF4_MEANS_LIMIT,
        'MEANS_DEA4_COUNT': config.MEANS_DEA4_COUNT,
        'DEA4_MEANS_LIMIT': config.DEA4_MEANS_LIMIT,

        # V5 均值参数 - 第一组 (1天)
        'MEANS_HIST1D_COUNT': config.MEANS_HIST1D_COUNT,
        'HIST1D_MEANS_LIMIT': config.HIST1D_MEANS_LIMIT,
        'MEANS_DIF1D_COUNT': config.MEANS_DIF1D_COUNT,
        'DIF1D_MEANS_LIMIT': config.DIF1D_MEANS_LIMIT,
        'MEANS_DEA1D_COUNT': config.MEANS_DEA1D_COUNT,
        'DEA1D_MEANS_LIMIT': config.DEA1D_MEANS_LIMIT,

        # V5 均值参数 - 第二组 (15分钟)
        'MEANS_HIST15_COUNT_2': config.MEANS_HIST15_COUNT_2,
        'HIST15_MEANS_LIMIT_2': config.HIST15_MEANS_LIMIT_2,
        'MEANS_DIF15_COUNT_2': config.MEANS_DIF15_COUNT_2,
        'DIF15_MEANS_LIMIT_2': config.DIF15_MEANS_LIMIT_2,
        'MEANS_DEA15_COUNT_2': config.MEANS_DEA15_COUNT_2,
        'DEA15_MEANS_LIMIT_2': config.DEA15_MEANS_LIMIT_2,

        # V5 均值参数 - 第二组 (1小时)
        'MEANS_HIST1H_COUNT_2': config.MEANS_HIST1H_COUNT_2,
        'HIST1H_MEANS_LIMIT_2': config.HIST1H_MEANS_LIMIT_2,
        'MEANS_DIF1H_COUNT_2': config.MEANS_DIF1H_COUNT_2,
        'DIF1H_MEANS_LIMIT_2': config.DIF1H_MEANS_LIMIT_2,
        'MEANS_DEA1H_COUNT_2': config.MEANS_DEA1H_COUNT_2,
        'DEA1H_MEANS_LIMIT_2': config.DEA1H_MEANS_LIMIT_2,

        # V5 均值参数 - 第二组 (4小时)
        'MEANS_HIST4_COUNT_2': config.MEANS_HIST4_COUNT_2,
        'HIST4_MEANS_LIMIT_2': config.HIST4_MEANS_LIMIT_2,
        'MEANS_DIF4_COUNT_2': config.MEANS_DIF4_COUNT_2,
        'DIF4_MEANS_LIMIT_2': config.DIF4_MEANS_LIMIT_2,
        'MEANS_DEA4_COUNT_2': config.MEANS_DEA4_COUNT_2,
        'DEA4_MEANS_LIMIT_2': config.DEA4_MEANS_LIMIT_2,

        # V5 均值参数 - 第二组 (1天)
        'MEANS_HIST1D_COUNT_2': config.MEANS_HIST1D_COUNT_2,
        'HIST1D_MEANS_LIMIT_2': config.HIST1D_MEANS_LIMIT_2,
        'MEANS_DIF1D_COUNT_2': config.MEANS_DIF1D_COUNT_2,
        'DIF1D_MEANS_LIMIT_2': config.DIF1D_MEANS_LIMIT_2,
        'MEANS_DEA1D_COUNT_2': config.MEANS_DEA1D_COUNT_2,
        'DEA1D_MEANS_LIMIT_2': config.DEA1D_MEANS_LIMIT_2,

        # V5.0 扩展参数
        'T1_T0_HIST_CHANGE': config.T1_T0_HIST_CHANGE,
        'T1_T0_DIF_CHANGE': config.T1_T0_DIF_CHANGE,
        'T1_T0_DEA_CHANGE': config.T1_T0_DEA_CHANGE,
        'T1_T0_HIST_LIMIT': config.T1_T0_HIST_LIMIT,
        'T1_HIST15_LIMIT': config.T1_HIST15_LIMIT,
        'T1_HIST15_MAX': config.T1_HIST15_MAX,
        'T1_DIF4_LIMIT': config.T1_DIF4_LIMIT,
        'T0_DEA4_LIMIT': config.T0_DEA4_LIMIT,
        'T0_HIST15_COUNT': config.T0_HIST15_COUNT,
        'T0_HIST15_LIMIT_MAX': config.T0_HIST15_LIMIT_MAX,

        # 价格变化参数
        'PRICE_CHANGE_LIMIT': config.PRICE_CHANGE_LIMIT,
        'PRICE_CHANGE_COUNT': config.PRICE_CHANGE_COUNT,
        'PRICE_CHANGE_LIMIT_B': config.PRICE_CHANGE_LIMIT_B,
        'PRICE_CHANGE_COUNT_B': config.PRICE_CHANGE_COUNT_B,
        'PRICE_CHANGE_LIMIT_C': config.PRICE_CHANGE_LIMIT_C,
        'PRICE_CHANGE_COUNT_C': config.PRICE_CHANGE_COUNT_C,
        'M_PRICE_CHANGE': config.M_PRICE_CHANGE,

        # 4H特殊参数
        'HIST4_EXTREME_LIMIT': config.HIST4_EXTREME_LIMIT,
        'HIST4_NEUTRAL_BAND': config.HIST4_NEUTRAL_BAND,
        'DIF4_T0_MIN_CHANGE': config.DIF4_T0_MIN_CHANGE,

        # MA5/MA10开关
        'ENABLE_MA5_MA10': config.ENABLE_MA5_MA10,

        # 止损持仓时间
        'STOP_LOSS_HOLD_TIME': config.STOP_LOSS_HOLD_TIME,

        # T0锁仓
        'T0_LOCK_ENABLED': config.T0_LOCK_ENABLED,

        # 仓位限制
        'NO_LIMIT_POS': config.NO_LIMIT_POS,
        'POSITION_NOMINAL': config.POSITION_NOMINAL,

        # 订单类型
        'OPEN_TAKER_OR_MAKER': config.OPEN_TAKER_OR_MAKER,

        # 手续费率
        'MAKER_FEE_RATE': config.MAKER_FEE_RATE,
        'TAKER_FEE_RATE': config.TAKER_FEE_RATE,
        'FEE_RATE': config.FEE_RATE,

        # 回测时间范围
        'DATE_FROM': config.DATE_FROM,
        'DATE_TO': config.DATE_TO,

        # 平仓参数
        'CLOSE_DECAY_POINTS': config.CLOSE_DECAY_POINTS,

        # 止损止盈
        'STOP_LOSS_POINTS': config.STOP_LOSS_POINTS,
        'TP_LEVELS': config.TP_LEVELS,
        'TP_RATIO_PER_LEVEL': config.TP_RATIO_PER_LEVEL,
        'DRAWDOWN_POINTS': config.DRAWDOWN_POINTS,
        'CLOSE_TIME_MINUTES': config.CLOSE_TIME_MINUTES,

        # 飞书配置
        'FEISHU_WEBHOOK': config.FEISHU_WEBHOOK,
        'FEISHU_ENABLED': config.FEISHU_ENABLED,

        # Web配置
        'WEB_HOST': config.WEB_HOST,
        'WEB_PORT': config.WEB_PORT,
        'WEB_ENABLED': config.WEB_ENABLED
    }


# ==================== 实时交易工作线程 ====================

def run_live_trading_worker():
    """
    实时交易工作线程 - 模拟盘/实盘模式
    从币安API实时获取K线数据并使用TradeEngine处理交易逻辑
    """
    try:
        from exchange_layer.exchange_factory import create_exchange
        from trade_module.trade_engine import TradeEngine

        logger.info("=" * 60)
        logger.info("开始实时交易")
        logger.info("=" * 60)

        # 确定当前模式
        current_mode = get_current_mode()
        is_simulation = (current_mode == 'simulation')

        # 创建交易所连接
        # 注意：模拟盘模式下，K线数据从实盘获取，订单操作用测试网
        logger.info("连接到交易所...")

        if is_simulation:
            # 模拟盘模式：创建两个连接
            logger.info("模式: 模拟盘")
            logger.info("  - K线数据: 币安实盘")
            logger.info("  - 订单操作: 币安测试网")

            # K线数据交易所（实盘）
            from exchange_layer.binance_exchange import BinanceExchange
            live_data['kline_exchange'] = BinanceExchange(
                api_key=config.BINANCE_LIVE_API_KEY,
                api_secret=config.BINANCE_LIVE_API_SECRET,
                testnet=False
            )

            # 订单操作交易所（测试网）
            live_data['order_exchange'] = BinanceExchange(
                api_key=config.BINANCE_TESTNET_API_KEY,
                api_secret=config.BINANCE_TESTNET_API_SECRET,
                testnet=True
            )

            # 连接两个交易所
            if not live_data['kline_exchange'].connect():
                logger.error("❌ K线数据交易所连接失败！")
                bot_state['connected'] = False
                socketio.emit('bot_state_changed', bot_state)
                return

            if not live_data['order_exchange'].connect():
                logger.error("❌ 订单操作交易所连接失败！")
                bot_state['connected'] = False
                socketio.emit('bot_state_changed', bot_state)
                return

            logger.info("✓ 已连接到币安实盘（K线数据）")
            logger.info("✓ 已连接到币安测试网（订单操作）")

        else:
            # 实盘模式：创建一个连接（实盘用于所有操作）
            logger.info("模式: 实盘")
            logger.info("  - K线数据: 币安实盘")
            logger.info("  - 订单操作: 币安实盘")

            live_data['kline_exchange'] = create_exchange()
            live_data['order_exchange'] = live_data['kline_exchange']

            if not live_data['kline_exchange'].connect():
                logger.error("❌ 交易所连接失败！")
                bot_state['connected'] = False
                socketio.emit('bot_state_changed', bot_state)
                return

            logger.info("✓ 已连接到币安实盘")

        bot_state['connected'] = True
        socketio.emit('bot_state_changed', bot_state)

        # 创建交易引擎
        logger.info("创建交易引擎...")

        # 根据模式设置正确的API密钥，供TradeEngine使用
        if is_simulation:
            # 模拟盘：TradeEngine使用测试网API密钥
            config.BINANCE_API_KEY = config.BINANCE_TESTNET_API_KEY
            config.BINANCE_API_SECRET = config.BINANCE_TESTNET_API_SECRET
            logger.info("交易引擎使用测试网API密钥（模拟盘）")
        else:
            # 实盘：TradeEngine使用实盘API密钥
            config.BINANCE_API_KEY = config.BINANCE_LIVE_API_KEY
            config.BINANCE_API_SECRET = config.BINANCE_LIVE_API_SECRET
            logger.info("交易引擎使用实盘API密钥")

        live_data['trade_engine'] = TradeEngine()
        logger.info("✓ 交易引擎已创建")

        # 预加载历史K线数据
        logger.info("预加载历史K线数据...")
        try:
            historical_klines = live_data['kline_exchange'].get_klines(
                symbol=config.SYMBOL,
                interval='1m',
                limit=1000
            )

            # 转换并存储到缓冲区
            for kline in historical_klines:
                live_data['klines_buffer'].append(kline)

            logger.info(f"✓ 已加载 {len(live_data['klines_buffer'])} 条历史K线")

            # 推送历史K线到前端
            socketio.emit('historical_klines_loaded', {
                'count': len(live_data['klines_buffer']),
                'latest_time': historical_klines[-1].open_time.strftime('%Y-%m-%d %H:%M:%S') if historical_klines else None
            })

        except Exception as e:
            logger.error(f"预加载历史K线失败: {e}")
            # 不阻塞后续流程

        # 清空停止事件
        live_data['stop_event'].clear()

        # 开始实时K线循环
        logger.info("开始实时K线监控...")
        logger.info(f"交易对: {config.SYMBOL}")
        logger.info(f"更新频率: 每60秒")

        while not live_data['stop_event'].is_set() and bot_state['running']:
            try:
                # 获取最新K线
                klines = live_data['kline_exchange'].get_klines(
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
                if live_data['latest_kline'] is None or new_kline.open_time != live_data['latest_kline'].open_time:
                    live_data['latest_kline'] = new_kline

                    # 添加到缓冲区
                    live_data['klines_buffer'].append(new_kline)
                    if len(live_data['klines_buffer']) > 1000:  # 保持最近1000条
                        live_data['klines_buffer'].pop(0)

                    # 推送新K线到前端
                    kline_data = {
                        'time': new_kline.open_time.strftime('%Y-%m-%d %H:%M:%S'),
                        'open': float(new_kline.open),
                        'high': float(new_kline.high),
                        'low': float(new_kline.low),
                        'close': float(new_kline.close),
                        'volume': float(new_kline.volume)
                    }
                    socketio.emit('new_kline', kline_data)

                    logger.info(
                        f"新K线: {kline_data['time']} | "
                        f"O:{kline_data['open']:.2f} "
                        f"H:{kline_data['high']:.2f} "
                        f"L:{kline_data['low']:.2f} "
                        f"C:{kline_data['close']:.2f}"
                    )

                    # 处理交易信号
                    if live_data['trade_engine']:
                        try:
                            tick_data = {
                                'open_time': new_kline.open_time,
                                'open': new_kline.open,
                                'high': new_kline.high,
                                'low': new_kline.low,
                                'close': new_kline.close,
                                'volume': new_kline.volume
                            }

                            # 简化处理：直接传给TradeEngine，不计算信号
                            # 实际信号计算应该在TradeEngine内部完成
                            live_data['trade_engine'].process_tick(
                                ts=new_kline.open_time,
                                row=tick_data,
                                signal=None
                            )
                        except Exception as e:
                            logger.error(f"处理交易信号失败: {e}")

                # 等待下一分钟
                time.sleep(60)

            except Exception as e:
                logger.error(f"实时K线监控出错: {e}", exc_info=True)
                time.sleep(30)

    except Exception as e:
        logger.error(f"实时交易工作线程错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 清理
        logger.info("实时交易工作线程结束")

        # 断开交易所连接
        if live_data['kline_exchange']:
            try:
                live_data['kline_exchange'].disconnect()
                logger.info("✓ K线数据交易所已断开")
            except Exception as e:
                logger.error(f"断开K线交易所失败: {e}")

        if live_data['order_exchange'] and live_data['order_exchange'] != live_data['kline_exchange']:
            try:
                live_data['order_exchange'].disconnect()
                logger.info("✓ 订单操作交易所已断开")
            except Exception as e:
                logger.error(f"断开订单交易所失败: {e}")

        # 清空交易所引用
        live_data['kline_exchange'] = None
        live_data['order_exchange'] = None

        bot_state['connected'] = False
        socketio.emit('bot_state_changed', bot_state)


# ==================== 回测工作线程 ====================

def run_session_backtest_worker(split_mode='day'):
    """
    会话模式回测工作线程 - 按时间阶段划分回测
    使用BacktestSessionManager管理会话,使用TradeEngine处理交易逻辑

    Args:
        split_mode: 会话划分模式 (day/week/month/custom)
    """
    try:
        import time
        from datetime import datetime

        import pandas as pd

        logger.info("=" * 60)
        logger.info("开始会话模式回测")
        logger.info(f"划分模式: {split_mode}")
        logger.info("=" * 60)

        # 更新连接状态
        bot_state['connected'] = True
        socketio.emit('bot_state_changed', bot_state)

        # 清理历史回测数据
        logger.info("清理历史回测数据...")
        try:
            import sqlite3
            conn = sqlite3.connect(
                config.DB_PATH,
                timeout=30.0,
                isolation_level=None
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM sim_log")
            old_simlog_count = cursor.fetchone()[0]
            logger.info(f"发现 {old_simlog_count} 条历史交易日志")

            cursor.execute("SELECT COUNT(*) FROM orders")
            old_orders_count = cursor.fetchone()[0]
            logger.info(f"发现 {old_orders_count} 条历史订单")

            cursor.execute("SELECT COUNT(*) FROM order_status_history")
            old_history_count = cursor.fetchone()[0]
            logger.info(f"发现 {old_history_count} 条订单状态历史")

            # 清空所有回测相关表
            cursor.execute("DELETE FROM sim_log")
            cursor.execute("DELETE FROM orders")
            cursor.execute("DELETE FROM order_status_history")
            conn.commit()
            conn.close()
            logger.info("✓ 历史数据已清理 (sim_log, orders, order_status_history)")

        except Exception as e:
            logger.error(f"清理历史数据失败: {e}")

        # 导入模块
        from data_module.db_kline_reader import DbKlineReader
        from signal_module.signal_calculator import SignalCalculator
        from trade_module import BacktestSessionManager, TradeEngine

        # 初始化
        session_manager = BacktestSessionManager()
        trade_engine = TradeEngine()
        signal_calculator = SignalCalculator()

        # 读取K线数据
        macd_table_name = 'klines_1m_macd_smooth_ma'
        logger.info(f"从MACD指标表读取数据: {macd_table_name}")

        reader = DbKlineReader(
            db_path=config.HIST_DB_PATH,
            table_name=macd_table_name
        )

        start_time_str = config.REPLAY_START
        end_time_str = config.REPLAY_END

        logger.info(f"获取K线数据: {start_time_str} 至 {end_time_str}")

        try:
            klines = reader.get_klines_by_time_range(
                start_time=start_time_str,
                end_time=end_time_str
            )

            if not klines:
                logger.warning("没有获取到K线数据，尝试获取最新数据")
                klines = reader.get_klines(limit=1000)

            logger.info(f"获取到 {len(klines)} 条K线数据")

            # 划分会话
            if split_mode == 'day':
                sessions = session_manager.split_by_day(klines)
            elif split_mode == 'week':
                sessions = session_manager.split_by_week(klines)
            elif split_mode == 'month':
                sessions = session_manager.split_by_month(klines)
            elif split_mode == 'custom':
                interval_hours = getattr(config, 'SESSION_INTERVAL_HOURS', 24)
                sessions = session_manager.split_by_custom(klines, interval_hours)
            else:
                logger.error(f"未知的划分模式: {split_mode}")
                return

            logger.info(f"划分为 {len(sessions)} 个会话")

            # 运行所有会话
            results = session_manager.run_all_sessions(
                sessions=sessions,
                trade_engine=trade_engine,
                signal_calculator=signal_calculator,
                socketio=socketio,
                bot_state=bot_state
            )

            # 打印会话摘要
            session_manager.print_session_summary(sessions)

            # 打印总体统计
            trade_engine.print_summary()

            # 保存交易日志到数据库
            logger.info("保存交易日志到数据库...")
            try:
                import sqlite3
                import time

                # 使用更长的超时时间并重试
                max_retries = 3
                retry_delay = 1
                write_conn = None
                
                for attempt in range(max_retries):
                    try:
                        write_conn = sqlite3.connect(
                            config.DB_PATH,
                            timeout=30.0,
                            isolation_level=None
                        )
                        # 启用WAL模式
                        write_conn.execute("PRAGMA journal_mode=WAL")
                        write_conn.execute("PRAGMA busy_timeout=30000")
                        write_cursor = write_conn.cursor()
                        write_cursor.execute("BEGIN TRANSACTION")
                        
                        inserted_count = 0
                        for log_entry in trade_engine.logs:
                            write_cursor.execute("""
                                INSERT INTO sim_log (
                                    log_time, event, side, price, contracts,
                                    pnl, details, fee_rate, fee_usd,
                                    trace_id, realized_pnl
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                str(log_entry[0]),
                                log_entry[1],
                                log_entry[2],
                                log_entry[3],
                                log_entry[4],
                                log_entry[5],
                                str(log_entry[6]),
                                log_entry[7],
                                log_entry[8],
                                log_entry[9],
                                log_entry[10]
                            ))
                            inserted_count += 1

                        write_conn.commit()
                        write_conn.close()
                        logger.info(f"✓ 已保存 {inserted_count} 条交易日志")
                        break
                        
                    except sqlite3.OperationalError as e:
                        if 'locked' in str(e).lower() and attempt < max_retries - 1:
                            logger.warning(f"数据库被锁，{retry_delay}秒后重试 ({attempt + 1}/{max_retries})...")
                            if write_conn:
                                write_conn.close()
                            time.sleep(retry_delay)
                            retry_delay *= 2
                        else:
                            raise

            except Exception as e:
                logger.error(f"保存交易日志失败: {e}", exc_info=True)

            # 通知前端回测完成
            final_stats = trade_engine.get_statistics()
            socketio.emit('backtest_complete', {
                'split_mode': split_mode,
                'total_sessions': len(sessions),
                'completed_sessions': len(results),
                'total_trades': final_stats['total_trades'],
                'winning_trades': final_stats['winning_trades'],
                'total_pnl_usd': final_stats['total_pnl_usd'],
                'final_capital_btc': final_stats['final_capital_btc'],
                'return_pct': final_stats['return_pct'],
                'sessions': results
            })

        except Exception as e:
            logger.error(f"回测过程出错: {e}")
            import traceback
            traceback.print_exc()

    except Exception as e:
        logger.error(f"会话模式回测工作线程错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 标记回测结束
        bot_state['running'] = False
        bot_state['connected'] = False
        socketio.emit('bot_state_changed', bot_state)
        logger.info("会话模式回测工作线程结束")


def run_backtest_worker():
    """
    回测工作线程 - 纯数据回放
    从数据库读取K线数据并模拟实时推送,使用TradeEngine处理交易逻辑
    """
    try:
        import time
        from datetime import datetime

        logger.info("=" * 60)
        logger.info("开始数据库回测")
        logger.info("=" * 60)

        # 更新连接状态
        bot_state['connected'] = True
        socketio.emit('bot_state_changed', bot_state)

        # 清理历史回测数据
        logger.info("清理历史回测数据...")
        try:
            import sqlite3

            conn = sqlite3.connect(
                config.DB_PATH,
                timeout=30.0,
                isolation_level=None
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM sim_log")
            old_simlog_count = cursor.fetchone()[0]
            logger.info(f"发现 {old_simlog_count} 条历史交易日志")

            cursor.execute("SELECT COUNT(*) FROM orders")
            old_orders_count = cursor.fetchone()[0]
            logger.info(f"发现 {old_orders_count} 条历史订单")

            cursor.execute("SELECT COUNT(*) FROM order_status_history")
            old_history_count = cursor.fetchone()[0]
            logger.info(f"发现 {old_history_count} 条订单状态历史")

            # 清空所有回测相关表
            cursor.execute("DELETE FROM sim_log")
            cursor.execute("DELETE FROM orders")
            cursor.execute("DELETE FROM order_status_history")
            conn.commit()
            conn.close()
            logger.info("✓ 历史数据已清理 (sim_log, orders, order_status_history)")

        except Exception as e:
            logger.error(f"清理历史数据失败: {e}")

        # 获取数据源 - 从MACD指标表读取
        from data_module.db_kline_reader import DbKlineReader
        from signal_module.signal_calculator import SignalCalculator
        from trade_module import TradeEngine

        # 初始化交易引擎
        trade_engine = TradeEngine()
        signal_calculator = SignalCalculator()

        # 使用包含MACD指标的表
        macd_table_name = 'klines_1m_macd_smooth_ma'
        logger.info(f"从MACD指标表读取数据: {macd_table_name}")

        reader = DbKlineReader(
            db_path=config.HIST_DB_PATH,
            table_name=macd_table_name
        )

        # 获取回测时间范围
        start_time_str = config.REPLAY_START
        end_time_str = config.REPLAY_END

        logger.info(f"获取K线数据: {start_time_str} 至 {end_time_str}")

        try:
            klines = reader.get_klines_by_time_range(
                start_time=start_time_str,
                end_time=end_time_str
            )

            if not klines:
                logger.warning("没有获取到K线数据，尝试获取最新数据")
                klines = reader.get_klines(limit=1000)

            logger.info(f"获取到 {len(klines)} 条K线数据")
            logger.info(klines[0])


            # 验证数据包含所需指标
            # if klines:
            #     sample = klines[0]
            #     required_fields = ['macd15m', 'dif15m', 'dea15m', 'j_15',
            #                      'macd1h', 'dif1h', 'dea1h', 'j_1h',
            #                      'macd4h', 'dif4h', 'dea4h', 'j_4h',
            #                      'macd1d', 'dif1d', 'dea1d', 'open_time']
            #     missing_fields = [f for f in required_fields if f not in sample]
            #     if missing_fields:
            #         logger.warning(f"K线数据缺少以下指标字段: {missing_fields}")
            #     else:
            #         logger.info("✓ K线数据包含所有必需的MACD和KDJ指标")

            processed_count = 0
            buy_signals = 0
            sell_signals = 0

            logger.info("开始回测 - 数据回放模式")
            # 预先构造价格序列,供价格波动过滤使用
            price_series = pd.Series([k.get('close', 0) for k in klines], dtype=float)
            price_window = max(config.PRICE_CHANGE_COUNT, config.PRICE_CHANGE_COUNT_B, config.PRICE_CHANGE_COUNT_C, 0)
            pre_kline = None
            for i, kline in enumerate(klines):
                # 检查是否应该停止
                if not bot_state['running']:
                    logger.info("回测被用户停止")
                    break

                # 每100条记录一次日志
                if i % 100 == 0:
                    stats = trade_engine.get_statistics()
                    # logger.info(
                    #     f"已处理 {i}/{len(klines)} 条K线 | "
                    #     f"信号: {buy_signals}多/{sell_signals}空 | "
                    #     f"开仓: {stats['positions_opened']}次 | "
                    #     f"当前资金: {stats['final_capital_btc']:.6f} BTC"
                    # )
                    # 更新进度到前端
                    socketio.emit('backtest_progress', {
                        'processed': i,
                        'total': len(klines),
                        'buy_signals': buy_signals,
                        'sell_signals': sell_signals,
                        'positions_opened': stats['positions_opened'],
                        'current_capital': stats['final_capital_btc']
                    })

                try:
                    # 计算交易信号前，先确认资金能覆盖至少1张合约
                    signal = None
                    if price_window > 0:
                        start_idx = max(0, i - price_window)
                        state_prices = price_series.iloc[start_idx:i]
                    else:
                        state_prices = pd.Series(dtype=float)

                    close_price = float(kline.get('close', 0) or 0.0)
                    can_afford_min_contract = True

                    if close_price <= 0:
                        can_afford_min_contract = False
                    elif not config.NO_LIMIT_POS:
                        available_capital = max(0.0, trade_engine.realized_pnl - trade_engine.locked_capital)
                        max_contracts = int((available_capital * close_price) / config.CONTRACT_NOTIONAL)
                        can_afford_min_contract = max_contracts >= 1

                    if can_afford_min_contract:
                        signal = signal_calculator.calculate_open_signal(kline, pre_kline, state_prices)

                    pre_kline = kline

                    # 发送开仓信号到前端用于图表标记
                    if signal and signal.action == 'open':
                        signal_type = 'buy' if signal.side == 'long' else 'sell'
                        signal_data = {
                            'type': signal_type,
                            'timestamp': str(kline.get('open_time')),
                            'price': float(kline.get('close', 0)),
                            'side': signal.side
                        }
                        logger.info(f"发送{signal_type}信号: {signal_data}")
                        socketio.emit('trade_signal', signal_data)

                    # 统计信号
                    if signal and signal.action == 'open':
                        if signal.side == 'long':
                            buy_signals += 1
                        else:
                            sell_signals += 1

                    # 使用交易引擎处理tick
                    # 转换kline为字典格式,确保包含时间戳
                    tick_data = dict(kline)
                    if 'open_time' in tick_data:
                        tick_data['ts'] = tick_data['open_time']

                    # 记录处理前的持仓数量,用于检测是否有平仓
                    positions_before = len(trade_engine.positions)

                    # 🔍 调试：记录传递给 process_tick 的信号
                    ts_str = str(tick_data.get('ts', ''))
                    if '19:44' in ts_str or '19:39' in ts_str:
                        logger.info(f"🔍 [web_app] 调用 process_tick: 时间={ts_str}")
                        logger.info(f"🔍 [web_app] signal={signal}")
                        if signal:
                            logger.info(f"🔍 [web_app] signal.action={signal.action if hasattr(signal, 'action') else 'N/A'}")
                            logger.info(f"🔍 [web_app] signal.side={signal.side if hasattr(signal, 'side') else 'N/A'}")
                        logger.info(f"🔍 [web_app] 当前持仓数={positions_before}")

                    trade_engine.process_tick(
                        ts=tick_data.get('ts'),
                        row=tick_data,
                        signal=signal
                    )

                    # 检测是否有平仓,发送平仓信号到前端
                    positions_after = len(trade_engine.positions)
                    if positions_after < positions_before:
                        # 有平仓发生,从最近的交易日志中获取平仓信息
                        if trade_engine.trades:
                            last_trade = trade_engine.trades[-1]
                            signal_data = {
                                'type': 'close',
                                'timestamp': str(last_trade.exit_time),
                                'price': float(last_trade.exit_price),
                                'side': last_trade.side,
                                'pnl': float(last_trade.net_pnl)
                            }
                            logger.info(f"发送平仓信号: {signal_data}")
                            socketio.emit('trade_signal', signal_data)

                except Exception as e:
                    logger.error(f"处理K线失败 (索引 {i}): {e}")
                    import traceback
                    traceback.print_exc()
                    # 继续处理下一条

                processed_count += 1


            # 回测完成 - 打印统计摘要
            logger.info("")
            logger.info("=" * 60)
            logger.info("回测完成")
            logger.info(f"总共处理: {processed_count} 条K线")
            logger.info(f"检测到信号: 多头{buy_signals}次 / 空头{sell_signals}次")
            logger.info(f"实际开仓: {trade_engine.triggers_count}次")
            logger.info("=" * 60)

            # 打印详细统计
            trade_engine.print_summary()

            # 保存交易日志到数据库
            logger.info("保存交易日志到数据库...")
            try:
                import sqlite3
                import time
                
                max_retries = 3
                retry_delay = 1
                write_conn = None
                
                for attempt in range(max_retries):
                    try:
                        write_conn = sqlite3.connect(
                            config.DB_PATH,
                            timeout=30.0,
                            isolation_level=None
                        )
                        # 启用WAL模式
                        write_conn.execute("PRAGMA journal_mode=WAL")
                        write_conn.execute("PRAGMA busy_timeout=30000")
                        write_cursor = write_conn.cursor()
                        write_cursor.execute("BEGIN TRANSACTION")
                        
                        inserted_count = 0
                        for log_entry in trade_engine.logs:
                            # log_entry格式: (time, event, side, price, contracts,
                            #                   pnl, details, fee_rate, fee_usd,
                            #                   trace_id, realized_pnl)
                            write_cursor.execute("""
                                INSERT INTO sim_log (
                                    log_time, event, side, price, contracts,
                                    pnl, details, fee_rate, fee_usd,
                                    trace_id, realized_pnl
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                str(log_entry[0]),      # log_time
                                log_entry[1],           # event
                                log_entry[2],           # side
                                log_entry[3],           # price
                                log_entry[4],           # contracts
                                log_entry[5],           # pnl
                                str(log_entry[6]),      # details
                                log_entry[7],           # fee_rate
                                log_entry[8],           # fee_usd
                                log_entry[9],           # trace_id
                                log_entry[10]           # realized_pnl
                            ))
                            inserted_count += 1

                        write_conn.commit()
                        write_conn.close()
                        logger.info(f"✓ 已保存 {inserted_count} 条交易日志")
                        break
                        
                    except sqlite3.OperationalError as e:
                        if 'locked' in str(e).lower() and attempt < max_retries - 1:
                            logger.warning(f"数据库被锁，{retry_delay}秒后重试 ({attempt + 1}/{max_retries})...")
                            if write_conn:
                                write_conn.close()
                            time.sleep(retry_delay)
                            retry_delay *= 2
                        else:
                            raise

            except Exception as e:
                logger.error(f"保存交易日志失败: {e}", exc_info=True)

            # 通知前端回测完成
            final_stats = trade_engine.get_statistics()
            socketio.emit('backtest_complete', {
                'processed': processed_count,
                'buy_signals': buy_signals,
                'sell_signals': sell_signals,
                'total_trades': final_stats['total_trades'],
                'winning_trades': final_stats['winning_trades'],
                'total_pnl_usd': final_stats['total_pnl_usd'],
                'final_capital_btc': final_stats['final_capital_btc'],
                'return_pct': final_stats['return_pct']
            })

        except Exception as e:
            logger.error(f"回测过程出错: {e}")
            import traceback
            traceback.print_exc()

    except Exception as e:
        logger.error(f"回测工作线程错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 标记回测结束
        bot_state['running'] = False
        bot_state['connected'] = False
        socketio.emit('bot_state_changed', bot_state)
        logger.info("回测工作线程结束")


# ==================== 启动函数 ====================

def run_web_server(debug=True):
    """
    启动Web服务器

    Args:
        debug: 是否开启调试模式(支持热重载)
            - True: 开发模式,自动重载代码变化
            - False: 生产模式,不自动重载
    """
    logger.info("=" * 60)
    logger.info("启动Web监控服务")
    logger.info("=" * 60)
    logger.info(f"运行模式: {'开发模式(热重载)' if debug else '生产模式'}")
    logger.info(f"访问地址: http://{config.WEB_HOST}:{config.WEB_PORT}")
    logger.info(f"配置页面: http://{config.WEB_HOST}:{config.WEB_PORT}/config")
    logger.info(f"监控页面: http://{config.WEB_HOST}:{config.WEB_PORT}/monitor")
    logger.info(f"参数页面: http://{config.WEB_HOST}:{config.WEB_PORT}/parameters")
    logger.info("=" * 60)

    if debug:
        logger.info("💡 开发模式已启用 - 代码修改后自动重载")
        logger.info("⚠️  注意: 调试模式不适合生产环境")

    # 开发模式参数
    dev_params = {
        'host': config.WEB_HOST,
        'port': config.WEB_PORT,
        'debug': debug,
        'use_reloader': debug,  # 自动重载
        'allow_unsafe_werkzeug': True
    }

    # 开发模式下的额外参数
    if debug:
        dev_params['extra_files'] = [
            'core/config.py',
            'signal_module/signal_calculator.py',
            'trade_module/trade_engine.py',
            'trade_module/backtest_session.py',
            'data_module/db_kline_reader.py',
        ]
        logger.info(f"监控文件: {len(dev_params['extra_files'])} 个")

    socketio.run(app, **dev_params)


if __name__ == '__main__':
    import sys

    # 检查命令行参数
    debug_mode = '--debug' in sys.argv or '-d' in sys.argv
    production_mode = '--prod' in sys.argv or '-p' in sys.argv

    # 如果没有指定模式,默认使用开发模式
    if not production_mode:
        debug_mode = True

    run_web_server(debug=debug_mode)
