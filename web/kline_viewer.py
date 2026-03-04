#!/usr/bin/env python3
"""
K线图Web查看器
从数据库读取K线数据，提供Web界面展示
参考币安风格，10秒自动刷新
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 先加载 .env 文件
from dotenv import load_dotenv

load_dotenv()

import json
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import requests
from flask import (Flask, jsonify, redirect, render_template, request, session,
                   url_for)

from core.config import config
from core.logger import get_logger

logger = get_logger('kline_viewer')

# 运行时参数文件路径（由交易引擎通过 SignalCalculator.export_signal_params() 导出）
_RUNNING_PARAMS_JSON = Path(__file__).parent.parent / 'data' / 'running_signal_params.json'


def _load_signal_params() -> dict:
    """从 running_signal_params.json 读取交易引擎实际运行时使用的参数。

    该文件由交易进程通过 SignalCalculator.export_signal_params() 导出，
    直接反映 signal_module 和 trade_engine 真正使用的 config 值。
    若文件不存在则回退到 config 单例。"""
    logger.info(f"尝试加载运行时参数文件: {_RUNNING_PARAMS_JSON}")
    if _RUNNING_PARAMS_JSON.exists():
        try:
            with open(_RUNNING_PARAMS_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    # 回退：从 config 取
    return {k.lower(): getattr(config, k) for k in dir(config) if k.isupper()}

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'kline-viewer-secret-change-this-in-production'

# 登录配置
ALLOWED_PHONES = config.ALLOWED_PHONES  # 从配置读取白名单列表
VERIFICATION_CODE_EXPIRY = 120  # 2分钟
SESSION_LIFETIME = 3600  # 1小时

# 验证码存储 {phone: {'code': str, 'expires': datetime, 'last_sent': datetime}}
verification_codes = {}

# 发送频率限制（秒）- 3分钟
SEND_CODE_INTERVAL = 180

# 数据库路径
DB_PATH = config.HIST_DB_PATH


def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login_page'))
        # 检查session是否过期
        if 'login_time' in session:
            login_time = datetime.fromisoformat(session['login_time'])
            if datetime.now() - login_time > timedelta(seconds=SESSION_LIFETIME):
                session.clear()
                return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/login', methods=['GET'])
def login_page():
    """登录页面"""
    if 'logged_in' in session:
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/api/send_code', methods=['POST'])
def send_verification_code():
    """发送验证码"""
    data = request.get_json()
    phone = data.get('phone', '').strip()

    if phone not in ALLOWED_PHONES:
        return jsonify({'success': False, 'error': '手机号未授权'}), 403

    # 检查发送频率限制（3分钟）
    stored = verification_codes.get(phone)
    if stored and 'last_sent' in stored:
        elapsed = (datetime.now() - stored['last_sent']).total_seconds()
        if elapsed < SEND_CODE_INTERVAL:
            remaining = int(SEND_CODE_INTERVAL - elapsed)
            return jsonify({
                'success': False,
                'error': f'请{remaining}秒后再试',
                'retry_after': remaining
            }), 429

    # 生成6位随机验证码
    code = ''.join([str(random.randint(0, 9)) for _ in range(6)])

    # 存储验证码，2分钟过期
    expires = datetime.now() + timedelta(seconds=VERIFICATION_CODE_EXPIRY)
    verification_codes[phone] = {
        'code': code,
        'expires': expires,
        'last_sent': datetime.now()
    }

    # 通过飞书发送验证码（强制发送，不依赖 FEISHU_ENABLED 开关）
    message = f"【验证码】您的登录验证码是：{code}，有效期2分钟，请勿泄露给他人。"

    # 直接调用飞书 API 发送
    success = False
    if config.FEISHU_WEBHOOK:
        try:
            response = requests.post(
                config.FEISHU_WEBHOOK,
                json={"msg_type": "text", "content": {"text": message}},
                timeout=5
            )
            success = response.status_code == 200
        except Exception as e:
            logger.error(f"飞书发送失败: {e}")

    if success:
        logger.info(f"验证码已发送至飞书，手机号: {phone[:3]}****{phone[-4:]}")
        return jsonify({
            'success': True,
            'message': '验证码已发送，请查看飞书消息',
            'expires_in': VERIFICATION_CODE_EXPIRY,
            'interval': SEND_CODE_INTERVAL
        })
    else:
        logger.error(f"飞书发送验证码失败")
        # 验证码只发送到飞书，不返回给前台
        return jsonify({
            'success': False,
            'error': '验证码发送失败，请检查飞书配置或稍后重试'
        }), 500


@app.route('/api/login', methods=['POST'])
def api_login():
    """登录验证"""
    data = request.get_json()
    phone = data.get('phone', '').strip()
    code = data.get('code', '').strip()

    if phone not in ALLOWED_PHONES:
        return jsonify({'success': False, 'error': '手机号未授权'}), 403

    # 验证验证码
    stored = verification_codes.get(phone)
    if not stored:
        return jsonify({'success': False, 'error': '请先获取验证码'}), 400

    if datetime.now() > stored['expires']:
        return jsonify({'success': False, 'error': '验证码已过期，请重新获取'}), 400

    if code != stored['code']:
        return jsonify({'success': False, 'error': '验证码错误'}), 400

    # 登录成功，设置session
    session['logged_in'] = True
    session['phone'] = phone
    session['login_time'] = datetime.now().isoformat()

    # 清除已使用的验证码
    del verification_codes[phone]

    logger.info(f"用户登录成功: {phone[:3]}****{phone[-4:]}")
    return jsonify({
        'success': True,
        'message': '登录成功',
        'session_expires_in': SESSION_LIFETIME
    })


@app.route('/logout')
def logout():
    """退出登录"""
    session.clear()
    return redirect(url_for('login_page'))


@app.route('/api/session')
def api_session():
    """检查session状态"""
    if 'logged_in' not in session:
        return jsonify({'logged_in': False})

    if 'login_time' in session:
        login_time = datetime.fromisoformat(session['login_time'])
        elapsed = (datetime.now() - login_time).total_seconds()
        remaining = SESSION_LIFETIME - elapsed

        if remaining <= 0:
            session.clear()
            return jsonify({'logged_in': False})

        return jsonify({
            'logged_in': True,
            'phone': session.get('phone', ''),
            'session_remaining': int(remaining)
        })

    return jsonify({'logged_in': False})


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def build_readonly_param_defaults():
    """构造与 start_backtest 模板字段兼容的默认参数。
    从 signal_module 导出的运行时参数读取（与交易引擎实际使用值一致）。"""
    # 从 signal_module 导出的运行时参数文件读取
    defaults = _load_signal_params()

    defaults.update({
        'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': defaults.get('version') or 'V5.0',
        'detailed_logging': defaults.get('detailed_logging', False),
        'open_maker_price_ratio': defaults.get('open_maker_price_ratio', ''),
        'open_maker_duration_minutes': defaults.get('open_maker_duration_minutes', ''),
        'timeout_close_ratio': defaults.get('timeout_close_ratio', ''),
        'mask_4h': defaults.get('mask_4h', ''),
    })
    return defaults


@app.route('/')
@login_required
def index():
    """主页面"""
    return render_template('kline_chart.html')


@app.route('/params')
@login_required
def params_page():
    """交易参数展示页面"""
    defaults = build_readonly_param_defaults()
    return render_template('trade_params.html', defaults=defaults)


@app.route('/logs')
@login_required
def logs_page():
    """日志查看页面"""
    return render_template('logs.html', log_path=config.TRADING_LOG_PATH)


@app.route('/api/logs')
@login_required
def api_logs():
    """获取日志内容API"""
    log_path = config.TRADING_LOG_PATH
    try:
        if not os.path.exists(log_path):
            return jsonify({'success': True, 'lines': [], 'path': log_path})

        # 读取最后200行
        lines = []
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            # 使用 collections.deque 高效读取最后N行
            from collections import deque
            lines = list(deque(f, maxlen=200))

        # 去除行尾换行符
        lines = [line.rstrip('\n\r') for line in lines]

        return jsonify({
            'success': True,
            'lines': lines,
            'path': log_path,
            'count': len(lines)
        })
    except Exception as e:
        logger.error(f"读取日志文件失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'path': log_path
        }), 500


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
    """获取交易参数配置（从 signal_module 导出的运行时参数读取，反映信号计算实际使用值）"""
    try:
        p = _load_signal_params()

        # 组织参数（从 JSON 字典取值，key 全小写）
        params = {
            '基础配置': {
                '交易对': p.get('symbol', config.SYMBOL),
                'K线间隔': p.get('kline_interval', config.KLINE_INTERVAL),
                '回测模式': config.REPLAY_MODE,
                '数据库模拟': config.DB_SIM_MODE,
                '版本': p.get('version', 'V5.0'),
                '参数快照时间': p.get('_exported_at', '未知'),
            },
            '仓位配置': {
                '初始资金(BTC)': p.get('position_btc', config.POSITION_BTC),
                '合约名义价值(USD)': p.get('contract_notional', config.CONTRACT_NOTIONAL),
                '杠杆倍数': p.get('leverage', config.LEVERAGE),
                '仓位名义价值': p.get('position_nominal', config.POSITION_NOMINAL),
                '无限制仓位': p.get('no_limit_pos', False),
            },
            'MACD指标参数': {
                'Fast周期': p.get('macd_fast', config.MACD_FAST),
                'Slow周期': p.get('macd_slow', config.MACD_SLOW),
                'Signal周期': p.get('macd_signal', config.MACD_SIGNAL),
            },
            'T0参数-15分钟': {
                'HIST上限': p.get('t0_hist15_limit', 9999),
                'HIST下限': p.get('t0_hist15_limit_min', 0),
                'HIST最大': p.get('t0_hist15_limit_max', -9999),
                'HIST计数': p.get('t0_hist15_count', 7),
                'DIF上限': p.get('t0_dif15_limit', 1000),
                'DIF下限': p.get('t0_dif15_limit_min', -9999),
                'J上限(多)': p.get('t0_j15m_limit', 999),
                'J下限(空)': p.get('t0_j15m_limit_kong', -999),
            },
            'T0参数-1小时': {
                'HIST上限': p.get('t0_hist1h_limit', 9999),
                'HIST下限': p.get('t0_hist1h_limit_min', 0),
                'DIF上限': p.get('t0_dif1h_limit', 1000),
                'DIF下限': p.get('t0_dif1h_limit_min', -9999),
                'J上限(多)': p.get('t0_j1h_limit', 999),
                'J下限(空)': p.get('t0_j1h_limit_kong', -999),
            },
            'T0参数-4小时': {
                'HIST上限': p.get('t0_hist4_limit', 9999),
                'HIST下限': p.get('t0_hist4_limit_min', 0),
                'DIF上限': p.get('t0_dif4_limit', 1000),
                'DIF下限': p.get('t0_dif4_limit_min', -1500),
                'J上限(多)': p.get('t0_j4h_limit', 113),
                'J下限(空)': p.get('t0_j4h_limit_kong', -13),
                'DEA4限制': p.get('t0_dea4_limit', -9999),
            },
            'T0参数-1天': {
                'HIST上限': p.get('t0_hist1d_limit', 9999),
                'HIST下限': p.get('t0_hist1d_limit_min', -9999),
                'DIF上限': p.get('t0_dif1d_limit', 9999),
                'DIF下限': p.get('t0_dif1d_limit_min', -9999),
                'HIST_1D限制': p.get('t0_hist_1D_limit', -999),
            },
            '均值参数-第一组(15m)': {
                'HIST均值数量': p.get('means_hist15_count', 5),
                'HIST均值限制': p.get('hist15_means_limit', 1),
                'DIF均值数量': p.get('means_dif15_count', 5),
                'DIF均值限制': p.get('dif15_means_limit', 1),
                'DEA均值数量': p.get('means_dea15_count', 5),
                'DEA均值限制': p.get('dea15_means_limit', 1),
            },
            '均值参数-第一组(1h)': {
                'HIST均值数量': p.get('means_hist1h_count', 5),
                'HIST均值限制': p.get('hist1h_means_limit', 1),
                'DIF均值数量': p.get('means_dif1h_count', 5),
                'DIF均值限制': p.get('dif1h_means_limit', 1),
                'DEA均值数量': p.get('means_dea1h_count', 5),
                'DEA均值限制': p.get('dea1h_means_limit', 1),
            },
            '均值参数-第一组(4h)': {
                'HIST均值数量': p.get('means_hist4_count', 5),
                'HIST均值限制': p.get('hist4_means_limit', 1),
                'DIF均值数量': p.get('means_dif4_count', 5),
                'DIF均值限制': p.get('dif4_means_limit', 1),
                'DEA均值数量': p.get('means_dea4_count', 5),
                'DEA均值限制': p.get('dea4_means_limit', 1),
            },
            '均值参数-第一组(1d)': {
                'HIST均值数量': p.get('means_hist1d_count', 360),
                'HIST均值限制': p.get('hist1d_means_limit', 0),
                'DIF均值数量': p.get('means_dif1d_count', 0),
                'DIF均值限制': p.get('dif1d_means_limit', 0),
                'DEA均值数量': p.get('means_dea1d_count', 0),
                'DEA均值限制': p.get('dea1d_means_limit', 0),
            },
            '均值参数-第二组(15m)': {
                'HIST均值数量': p.get('means_hist15_count_2', 10),
                'HIST均值限制': p.get('hist15_means_limit_2', 1),
                'DIF均值数量': p.get('means_dif15_count_2', 60),
                'DIF均值限制': p.get('dif15_means_limit_2', 1),
                'DEA均值数量': p.get('means_dea15_count_2', 10),
                'DEA均值限制': p.get('dea15_means_limit_2', 1),
            },
            '均值参数-第二组(1h)': {
                'HIST均值数量': p.get('means_hist1h_count_2', 10),
                'HIST均值限制': p.get('hist1h_means_limit_2', 1),
                'DIF均值数量': p.get('means_dif1h_count_2', 10),
                'DIF均值限制': p.get('dif1h_means_limit_2', 1),
                'DEA均值数量': p.get('means_dea1h_count_2', 15),
                'DEA均值限制': p.get('dea1h_means_limit_2', 1),
            },
            '均值参数-第二组(4h)': {
                'HIST均值数量': p.get('means_hist4_count_2', 10),
                'HIST均值限制': p.get('hist4_means_limit_2', 1),
                'DIF均值数量': p.get('means_dif4_count_2', 10),
                'DIF均值限制': p.get('dif4_means_limit_2', 1),
                'DEA均值数量': p.get('means_dea4_count_2', 10),
                'DEA均值限制': p.get('dea4_means_limit_2', -3),
            },
            '均值参数-第二组(1d)': {
                'HIST均值数量': p.get('means_hist1d_count_2', 0),
                'HIST均值限制': p.get('hist1d_means_limit_2', 0),
                'DIF均值数量': p.get('means_dif1d_count_2', 120),
                'DIF均值限制': p.get('dif1d_means_limit_2', 0),
                'DEA均值数量': p.get('means_dea1d_count_2', 0),
                'DEA均值限制': p.get('dea1d_means_limit_2', 0),
            },
            '止盈止损': {
                '止损比例': p.get('stop_loss_points', 0.02),
                '止盈级别': p.get('tp_levels', [1.006, 1.012, 1.018, 1.024, 1.03]),
                '止盈每级比例': p.get('tp_ratio_per_level', 0.0),
                '回撤比例': p.get('drawdown_points', 0.0002),
                '止损持仓时间': p.get('stop_loss_hold_time', 0),
                '超时平仓分钟': p.get('close_time_minutes', 9999),
                '超时衰减点数': p.get('close_decay_points', 9999),
                '超时平仓比例': p.get('timeout_close_ratio', 0.0001),
            },
            '价格变化参数': {
                '价格变化限制A': p.get('price_change_limit', 0.02),
                '价格变化计数A': p.get('price_change_count', 5),
                '价格变化限制B': p.get('price_change_limit_b', 0.025),
                '价格变化计数B': p.get('price_change_count_b', 10),
                '价格变化限制C': p.get('price_change_limit_c', 0.03),
                '价格变化计数C': p.get('price_change_count_c', 60),
                '价格变化限制D': p.get('price_change_limit_d', 0.01),
                '价格变化计数D': p.get('price_change_count_d', 0),
                '价格变化限制E': p.get('price_change_limit_e', 0.01),
                '价格变化计数E': p.get('price_change_count_e', 0),
                '分钟价格变化A': p.get('m_price_change', 0.008),
                '分钟数A': p.get('m_price_change_minutes', 1),
                '分钟价格变化B': p.get('m_price_change_b', 0.012),
                '分钟数B': p.get('m_price_change_minutes_b', 5),
                '分钟价格变化C': p.get('m_price_change_c', 0.015),
                '分钟数C': p.get('m_price_change_minutes_c', 10),
                '分钟价格变化D': p.get('m_price_change_d', 0.9999),
                '分钟数D': p.get('m_price_change_minutes_d', 30),
                '分钟价格变化E': p.get('m_price_change_e', 0.9999),
                '分钟数E': p.get('m_price_change_minutes_e', 60),
            },
            'T1参数': {
                'T0_HIST变化': p.get('t1_t0_hist_change', 15),
                'T0_DIF变化': p.get('t1_t0_dif_change', 15),
                'T0_DEA变化': p.get('t1_t0_dea_change', -9999),
                'T0_HIST限制': p.get('t1_t0_hist_limit', -9999),
                'HIST15限制': p.get('t1_hist15_limit', 30),
                'HIST15最大': p.get('t1_hist15_max', 50),
                'DIF4限制': p.get('t1_dif4_limit', 1200),
            },
            '特殊参数': {
                '4H极端限制': p.get('hist4_extreme_limit', 9999),
                '4H中性区间': p.get('hist4_neutral_band', 0),
                'DIF4_T0最小变化': p.get('dif4_t0_min_change', 9999),
                '启用MA5/MA10': p.get('enable_ma5_ma10', False),
                'T0锁仓': p.get('t0_lock_enabled', False),
            },
            '手续费': {
                'Maker费率': p.get('maker_fee_rate', 0.0002),
                'Taker费率': p.get('taker_fee_rate', 0.0006),
                '默认费率': p.get('fee_rate', 0.0004),
                '开仓类型': p.get('open_taker_or_maker', 'TAKER'),
                'Maker价格比例': p.get('open_maker_price_ratio', 0.0),
                'Maker持续分钟': p.get('open_maker_duration_minutes', 3),
            },
        }

        return jsonify({'success': True, 'data': params})

    except Exception as e:
        logger.error(f"获取配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/trades')
def api_trades():
    """获取交易记录（按持仓/订单维度聚合）"""
    limit = int(request.args.get('limit', 100))
    start_time = request.args.get('start_time', None)
    end_time = request.args.get('end_time', None)
    view_mode = request.args.get('view_mode', 'position')  # 'position' 或 'trade'

    try:
        from core.trade_recorder import get_trade_recorder

        recorder = get_trade_recorder()

        # 默认按持仓维度展示
        if view_mode == 'trade':
            # 返回原始交易明细
            trades = recorder.get_trades(
                start_time=start_time,
                end_time=end_time,
                limit=limit
            )
            return jsonify({'success': True, 'data': trades, 'view_mode': 'trade'})
        else:
            # 按持仓维度聚合展示
            positions = recorder.get_positions(
                status=None,  # 获取所有状态
                limit=limit
            )

            # 格式化持仓数据为订单维度
            orders = []
            for pos in positions:
                # 查询该持仓下的所有交易明细用于统计
                trades_in_pos = recorder.get_trades(
                    position_id=pos.get('position_id'),
                    limit=100
                )

                # 统计止盈次数
                tp_count = sum(1 for t in trades_in_pos if t.get('action') == 'TP')

                orders.append({
                    'order_id': pos.get('position_id'),
                    'trace_id': pos.get('trace_id'),
                    'symbol': pos.get('symbol', 'BTCUSD_PERP'),
                    'side': pos.get('side'),
                    'status': pos.get('status'),
                    # 开仓信息
                    'entry_time': pos.get('open_time'),
                    'entry_price': pos.get('entry_price'),
                    'entry_contracts': pos.get('entry_contracts'),
                    # 平仓信息
                    'exit_time': pos.get('close_time'),
                    'exit_price': pos.get('exit_price'),
                    'exit_contracts': pos.get('exit_contracts'),
                    # 盈亏统计
                    'gross_pnl': pos.get('gross_pnl'),
                    'net_pnl': pos.get('net_pnl'),
                    'total_fee': pos.get('total_fee_usd'),
                    # 平仓原因
                    'exit_reason': pos.get('exit_reason'),
                    'tp_levels_hit': pos.get('tp_levels_hit'),
                    'tp_count': tp_count,
                    # 交易明细数量
                    'trade_count': len(trades_in_pos)
                })

            return jsonify({'success': True, 'data': orders, 'view_mode': 'position'})

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
