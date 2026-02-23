#!/usr/bin/env python3
"""
K线图Web查看器
从数据库读取K线数据，提供Web界面展示
参考币安风格，10秒自动刷新
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, render_template, request

from core.config import config
from core.logger import get_logger

logger = get_logger('kline_viewer')

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'kline-viewer-secret'

# 数据库路径
DB_PATH = config.HIST_DB_PATH


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/')
def index():
    """主页面"""
    return render_template('kline_chart.html')


@app.route('/params')
def params_page():
    """交易参数展示页面"""
    return render_template('trade_params.html')


@app.route('/api/klines')
def api_klines():
    """
    获取K线数据API
    
    参数:
        table: 数据表名 (默认 klines_1m_macd_smooth_ma)
        limit: 返回条数 (默认 500)
        end_time: 结束时间 (可选)
    """
    table = request.args.get('table', 'klines_1m_macd_smooth_ma')
    limit = int(request.args.get('limit', 500))
    end_time = request.args.get('end_time', None)
    
    # 安全检查表名
    allowed_tables = ['klines_1m', 'klines_1m_macd_smooth_ma', 'klines_1m_sim']
    if table not in allowed_tables:
        table = 'klines_1m'
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 构建查询
        if end_time:
            sql = f"""
                SELECT * FROM {table}
                WHERE open_time <= ?
                ORDER BY open_time DESC
                LIMIT ?
            """
            cursor.execute(sql, (end_time, limit))
        else:
            sql = f"""
                SELECT * FROM {table}
                ORDER BY open_time DESC
                LIMIT ?
            """
            cursor.execute(sql, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        # 转换为K线数据格式（按时间正序）
        klines = []
        for row in reversed(rows):
            # 解析时间 - 数据库存储的是UTC时间
            open_time_str = row['open_time']
            try:
                # 尝试使用 fromisoformat 解析（支持带时区的格式）
                dt = datetime.fromisoformat(open_time_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except ValueError:
                # 如果失败，尝试不带时区的格式
                try:
                    dt = datetime.strptime(open_time_str, '%Y-%m-%d %H:%M:%S')
                    dt = dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    # 最后尝试去掉时区后缀
                    clean_time = open_time_str.replace('+00:00', '').replace('Z', '')
                    dt = datetime.fromisoformat(clean_time)
                    dt = dt.replace(tzinfo=timezone.utc)
            
            kline = {
                'time': int(dt.timestamp()),
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': float(row['volume']) if row['volume'] else 0,
            }
            
            # 如果有MACD数据 (klines_1m_macd_smooth_ma表)
            row_keys = row.keys()
            
            # 15分钟指标
            if 'dif15m' in row_keys:
                kline['dif15m'] = float(row['dif15m']) if row['dif15m'] else None
            if 'dea15m' in row_keys:
                kline['dea15m'] = float(row['dea15m']) if row['dea15m'] else None
            if 'macd15m' in row_keys:
                kline['macd15m'] = float(row['macd15m']) if row['macd15m'] else None
            
            # 4小时指标
            if 'dif4h' in row_keys:
                kline['dif4h'] = float(row['dif4h']) if row['dif4h'] else None
            if 'dea4h' in row_keys:
                kline['dea4h'] = float(row['dea4h']) if row['dea4h'] else None
            if 'macd4h' in row_keys:
                kline['macd4h'] = float(row['macd4h']) if row['macd4h'] else None
            
            # 1小时指标
            if 'dif1h' in row_keys:
                kline['dif1h'] = float(row['dif1h']) if row['dif1h'] else None
            if 'dea1h' in row_keys:
                kline['dea1h'] = float(row['dea1h']) if row['dea1h'] else None
            if 'macd1h' in row_keys:
                kline['macd1h'] = float(row['macd1h']) if row['macd1h'] else None
            
            # 旧版MACD字段兼容
            if 'macd' in row_keys:
                kline['macd'] = float(row['macd']) if row['macd'] else None
                kline['signal'] = float(row['signal']) if row['signal'] else None
                kline['histogram'] = float(row['histogram']) if row['histogram'] else None
            
            klines.append(kline)
        
        return jsonify({
            'success': True,
            'data': klines,
            'count': len(klines),
            'table': table
        })
        
    except Exception as e:
        logger.error(f"获取K线数据失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/latest')
def api_latest():
    """获取最新一条K线数据"""
    table = request.args.get('table', 'klines_1m_macd_smooth_ma')
    
    allowed_tables = ['klines_1m', 'klines_1m_macd_smooth_ma', 'klines_1m_sim']
    if table not in allowed_tables:
        table = 'klines_1m'
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(f"SELECT * FROM {table} ORDER BY open_time DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        
        if row:
            open_time_str = row['open_time']
            try:
                dt = datetime.fromisoformat(open_time_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except ValueError:
                try:
                    dt = datetime.strptime(open_time_str, '%Y-%m-%d %H:%M:%S')
                    dt = dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    clean_time = open_time_str.replace('+00:00', '').replace('Z', '')
                    dt = datetime.fromisoformat(clean_time)
                    dt = dt.replace(tzinfo=timezone.utc)
            
            data = {
                'time': int(dt.timestamp()),
                'open_time': open_time_str,
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': float(row['volume']) if row['volume'] else 0,
            }
            
            if 'macd' in row.keys():
                data['macd'] = float(row['macd']) if row['macd'] else None
                data['signal'] = float(row['signal']) if row['signal'] else None
                data['histogram'] = float(row['histogram']) if row['histogram'] else None
            
            return jsonify({'success': True, 'data': data})
        
        return jsonify({'success': False, 'error': 'No data'})
        
    except Exception as e:
        logger.error(f"获取最新K线失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stats')
def api_stats():
    """获取数据统计信息"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # 各表的记录数和时间范围
        tables = ['klines_1m', 'klines_1m_macd_smooth_ma']
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
                count = cursor.fetchone()['count']
                
                cursor.execute(f"""
                    SELECT MIN(open_time) as min_time, MAX(open_time) as max_time 
                    FROM {table}
                """)
                time_range = cursor.fetchone()
                
                stats[table] = {
                    'count': count,
                    'min_time': time_range['min_time'],
                    'max_time': time_range['max_time']
                }
            except:
                stats[table] = {'count': 0, 'min_time': None, 'max_time': None}
        
        conn.close()
        return jsonify({'success': True, 'data': stats})
        
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/orders')
def api_orders():
    """获取订单列表"""
    limit = int(request.args.get('limit', 50))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 查询订单表
        cursor.execute("""
            SELECT * FROM orders 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
        
        orders = []
        for row in rows:
            orders.append({
                'order_id': row['order_id'] if 'order_id' in row.keys() else row['id'],
                'time': row['created_at'] if 'created_at' in row.keys() else '',
                'symbol': row['symbol'] if 'symbol' in row.keys() else 'BTCUSD_PERP',
                'side': row['side'] if 'side' in row.keys() else '',
                'type': row['order_type'] if 'order_type' in row.keys() else '',
                'price': float(row['price']) if row.get('price') else None,
                'quantity': float(row['quantity']) if row.get('quantity') else 0,
                'filled_price': float(row['filled_price']) if row.get('filled_price') else None,
                'status': row['status'] if 'status' in row.keys() else '',
            })
        
        return jsonify({'success': True, 'data': orders})
        
    except Exception as e:
        logger.error(f"获取订单失败: {e}")
        return jsonify({'success': True, 'data': []})


@app.route('/api/positions')
def api_positions():
    """获取持仓信息"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 尝试从 sim_log 表获取最新持仓信息
        try:
            cursor.execute("""
                SELECT * FROM sim_log 
                WHERE position_qty > 0 OR position_qty < 0
                ORDER BY log_time DESC 
                LIMIT 1
            """)
            row = cursor.fetchone()
            
            if row:
                # 获取最新价格
                cursor.execute("SELECT close FROM klines_1m ORDER BY open_time DESC LIMIT 1")
                price_row = cursor.fetchone()
                current_price = float(price_row['close']) if price_row else 0
                
                qty = float(row['position_qty']) if row['position_qty'] else 0
                entry = float(row['entry_price']) if row.get('entry_price') else 0
                
                if qty != 0:
                    unrealized = (current_price - entry) * qty if qty > 0 else (entry - current_price) * abs(qty)
                    positions = [{
                        'symbol': 'BTCUSD_PERP',
                        'side': 'LONG' if qty > 0 else 'SHORT',
                        'quantity': abs(qty),
                        'entry_price': entry,
                        'current_price': current_price,
                        'unrealized_pnl': unrealized,
                    }]
                    conn.close()
                    return jsonify({'success': True, 'data': positions})
        except:
            pass
        
        conn.close()
        return jsonify({'success': True, 'data': []})
        
    except Exception as e:
        logger.error(f"获取持仓失败: {e}")
        return jsonify({'success': True, 'data': []})


@app.route('/api/balance')
def api_balance():
    """获取资金信息"""
    try:
        # 尝试从交易引擎获取实时余额
        try:
            from exchange_layer.exchange_factory import create_exchange
            exchange = create_exchange(testnet=True)
            if exchange.connect():
                info = exchange.get_account_info('BTC')
                return jsonify({
                    'success': True,
                    'data': {
                        'total_wallet_balance': info.total_wallet_balance,
                        'available_balance': info.available_balance,
                        'unrealized_pnl': info.unrealized_pnl,
                        'margin_balance': info.total_wallet_balance + info.unrealized_pnl,
                    }
                })
        except Exception as e:
            logger.warning(f"从交易所获取余额失败: {e}")
        
        # 从数据库获取模拟余额
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT * FROM sim_log 
                ORDER BY log_time DESC 
                LIMIT 1
            """)
            row = cursor.fetchone()
            
            if row and 'balance' in row.keys():
                conn.close()
                return jsonify({
                    'success': True,
                    'data': {
                        'total_wallet_balance': float(row['balance']) if row['balance'] else 0,
                        'available_balance': float(row['balance']) if row['balance'] else 0,
                        'unrealized_pnl': 0,
                        'margin_balance': float(row['balance']) if row['balance'] else 0,
                    }
                })
        except:
            pass
        
        conn.close()
        return jsonify({'success': True, 'data': None})
        
    except Exception as e:
        logger.error(f"获取资金失败: {e}")
        return jsonify({'success': True, 'data': None})


@app.route('/api/events')
def api_events():
    """获取事件日志"""
    limit = int(request.args.get('limit', 50))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        events = []
        
        # 尝试从 sim_log 获取事件
        try:
            cursor.execute("""
                SELECT log_time, action, reason, details 
                FROM sim_log 
                ORDER BY log_time DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            
            for row in rows:
                action = row['action'] if 'action' in row.keys() else ''
                level = 'SUCCESS' if action in ['OPEN', 'CLOSE', 'TP', 'SL'] else 'INFO'
                if 'error' in str(row.get('details', '')).lower():
                    level = 'ERROR'
                
                events.append({
                    'time': row['log_time'],
                    'level': level,
                    'message': f"[{action}] {row.get('reason', '')} {row.get('details', '')}",
                })
        except:
            pass
        
        # 尝试从 order_status_history 获取事件
        try:
            cursor.execute("""
                SELECT created_at, order_id, old_status, new_status 
                FROM order_status_history 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            
            for row in rows:
                events.append({
                    'time': row['created_at'],
                    'level': 'INFO',
                    'message': f"订单 {row['order_id']} 状态变更: {row['old_status']} -> {row['new_status']}",
                })
        except:
            pass
        
        # 按时间排序
        events.sort(key=lambda x: x['time'] if x['time'] else '', reverse=True)
        
        conn.close()
        return jsonify({'success': True, 'data': events[:limit]})
        
    except Exception as e:
        logger.error(f"获取事件失败: {e}")
        return jsonify({'success': True, 'data': []})


@app.route('/api/config')
def api_config():
    """获取交易参数配置"""
    try:
        from core.config import config

        # 组织参数
        params = {
            '基础配置': {
                '交易对': config.SYMBOL,
                'K线间隔': config.KLINE_INTERVAL,
                '回测模式': config.REPLAY_MODE,
                '数据库模拟': config.DB_SIM_MODE,
            },
            '仓位配置': {
                '初始资金(BTC)': config.POSITION_BTC,
                '合约名义价值(USD)': config.CONTRACT_NOTIONAL,
                '杠杆倍数': config.LEVERAGE,
                '仓位名义价值': config.POSITION_NOMINAL,
            },
            'MACD指标参数': {
                'Fast周期': config.MACD_FAST,
                'Slow周期': config.MACD_SLOW,
                'Signal周期': config.MACD_SIGNAL,
            },
            'T0参数-15分钟': {
                'HIST上限': config.T0_HIST15_LIMIT,
                'HIST下限': config.T0_HIST15_LIMIT_MIN,
                'DIF上限': config.T0_DIF15_LIMIT,
                'DIF下限': config.T0_DIF15_LIMIT_MIN,
                'J上限(多)': config.T0_J15M_LIMIT,
                'J下限(空)': config.T0_J15M_LIMIT_KONG,
            },
            'T0参数-1小时': {
                'HIST上限': config.T0_HIST1H_LIMIT,
                'HIST下限': config.T0_HIST1H_LIMIT_MIN,
                'DIF上限': config.T0_DIF1H_LIMIT,
                'DIF下限': config.T0_DIF1H_LIMIT_MIN,
                'J上限(多)': config.T0_J1H_LIMIT,
                'J下限(空)': config.T0_J1H_LIMIT_KONG,
            },
            'T0参数-4小时': {
                'HIST上限': config.T0_HIST4_LIMIT,
                'HIST下限': config.T0_HIST4_LIMIT_MIN,
                'DIF上限': config.T0_DIF4_LIMIT,
                'DIF下限': config.T0_DIF4_LIMIT_MIN,
                'J上限(多)': config.T0_J4H_LIMIT,
                'J下限(空)': config.T0_J4H_LIMIT_KONG,
            },
            'T0参数-1天': {
                'HIST上限': config.T0_HIST1D_LIMIT,
                'HIST下限': config.T0_HIST1D_LIMIT_MIN,
                'DIF上限': config.T0_DIF1D_LIMIT,
                'DIF下限': config.T0_DIF1D_LIMIT_MIN,
            },
            '均值参数-第一组(15m)': {
                'HIST均值数量': config.MEANS_HIST15_COUNT,
                'HIST均值限制': config.HIST15_MEANS_LIMIT,
                'DIF均值数量': config.MEANS_DIF15_COUNT,
                'DIF均值限制': config.DIF15_MEANS_LIMIT,
                'DEA均值数量': config.MEANS_DEA15_COUNT,
                'DEA均值限制': config.DEA15_MEANS_LIMIT,
            },
            '均值参数-第一组(1h)': {
                'HIST均值数量': config.MEANS_HIST1H_COUNT,
                'HIST均值限制': config.HIST1H_MEANS_LIMIT,
                'DIF均值数量': config.MEANS_DIF1H_COUNT,
                'DIF均值限制': config.DIF1H_MEANS_LIMIT,
                'DEA均值数量': config.MEANS_DEA1H_COUNT,
                'DEA均值限制': config.DEA1H_MEANS_LIMIT,
            },
            '均值参数-第一组(4h)': {
                'HIST均值数量': config.MEANS_HIST4_COUNT,
                'HIST均值限制': config.HIST4_MEANS_LIMIT,
                'DIF均值数量': config.MEANS_DIF4_COUNT,
                'DIF均值限制': config.DIF4_MEANS_LIMIT,
                'DEA均值数量': config.MEANS_DEA4_COUNT,
                'DEA均值限制': config.DEA4_MEANS_LIMIT,
            },
            '均值参数-第二组(15m)': {
                'HIST均值数量': config.MEANS_HIST15_COUNT_2,
                'HIST均值限制': config.HIST15_MEANS_LIMIT_2,
                'DIF均值数量': config.MEANS_DIF15_COUNT_2,
                'DIF均值限制': config.DIF15_MEANS_LIMIT_2,
                'DEA均值数量': config.MEANS_DEA15_COUNT_2,
                'DEA均值限制': config.DEA15_MEANS_LIMIT_2,
            },
            '均值参数-第二组(1h)': {
                'HIST均值数量': config.MEANS_HIST1H_COUNT_2,
                'HIST均值限制': config.HIST1H_MEANS_LIMIT_2,
                'DIF均值数量': config.MEANS_DIF1H_COUNT_2,
                'DIF均值限制': config.DIF1H_MEANS_LIMIT_2,
                'DEA均值数量': config.MEANS_DEA1H_COUNT_2,
                'DEA均值限制': config.DEA1H_MEANS_LIMIT_2,
            },
            '止盈止损': {
                '止损比例': config.STOP_LOSS_POINTS,
                '止盈级别': config.TP_LEVELS,
                '回撤比例': config.DRAWDOWN_POINTS,
                '止损持仓时间': config.STOP_LOSS_HOLD_TIME,
            },
            '价格变化参数': {
                '价格变化限制A': config.PRICE_CHANGE_LIMIT,
                '价格变化计数A': config.PRICE_CHANGE_COUNT,
                '价格变化限制B': config.PRICE_CHANGE_LIMIT_B,
                '价格变化计数B': config.PRICE_CHANGE_COUNT_B,
                '分钟价格变化A': config.M_PRICE_CHANGE,
                '分钟数A': config.M_PRICE_CHANGE_MINUTES,
                '分钟价格变化B': config.M_PRICE_CHANGE_B,
                '分钟数B': config.M_PRICE_CHANGE_MINUTES_B,
            },
            'T1参数': {
                'T0_HIST变化': config.T1_T0_HIST_CHANGE,
                'T0_DIF变化': config.T1_T0_DIF_CHANGE,
                'HIST15限制': config.T1_HIST15_LIMIT,
                'HIST15最大': config.T1_HIST15_MAX,
                'DIF4限制': config.T1_DIF4_LIMIT,
            },
            '特殊参数': {
                '4H极端限制': config.HIST4_EXTREME_LIMIT,
                '4H中性区间': config.HIST4_NEUTRAL_BAND,
                '启用MA5/MA10': config.ENABLE_MA5_MA10,
                'T0锁仓': config.T0_LOCK_ENABLED,
            },
            '手续费': {
                'Maker费率': config.MAKER_FEE_RATE,
                'Taker费率': config.TAKER_FEE_RATE,
                '默认费率': config.FEE_RATE,
                '开仓类型': config.OPEN_TAKER_OR_MAKER,
            },
        }

        return jsonify({'success': True, 'data': params})

    except Exception as e:
        logger.error(f"获取配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/trades')
def api_trades():
    """获取交易记录"""
    limit = int(request.args.get('limit', 100))
    start_time = request.args.get('start_time', None)
    end_time = request.args.get('end_time', None)

    try:
        from core.trade_recorder import get_trade_recorder

        recorder = get_trade_recorder()
        trades = recorder.get_trades(
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )

        return jsonify({'success': True, 'data': trades})

    except Exception as e:
        logger.error(f"获取交易记录失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/positions')
def api_positions_v2():
    """获取持仓记录"""
    status = request.args.get('status', None)
    limit = int(request.args.get('limit', 100))

    try:
        from core.trade_recorder import get_trade_recorder

        recorder = get_trade_recorder()
        positions = recorder.get_positions(status=status, limit=limit)

        return jsonify({'success': True, 'data': positions})

    except Exception as e:
        logger.error(f"获取持仓记录失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/trade_summary')
def api_trade_summary():
    """获取交易汇总统计"""
    try:
        from core.trade_recorder import get_trade_recorder

        recorder = get_trade_recorder()
        summary = recorder.get_trade_summary()

        return jsonify({'success': True, 'data': summary})

    except Exception as e:
        logger.error(f"获取交易汇总失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='K线图Web查看器')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址')
    parser.add_argument('--port', type=int, default=6000, help='端口号')
    parser.add_argument('--debug', action='store_true', help='调试模式')
    args = parser.parse_args()
    
    logger.info(f"启动K线图Web查看器: http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)
