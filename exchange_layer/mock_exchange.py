#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地模拟交易所 - 从数据库读取历史数据，模拟订单执行
"""

import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.config import config
from core.logger import get_logger
from trade_module.local_order import LocalOrderManager
from trade_module.local_order import Order as LocalOrder

from .base_exchange import BaseExchange
from .models import (AccountInfo, Kline, Order, OrderSide, OrderStatus,
                     OrderType)


class MockExchange(BaseExchange):
    """
    本地模拟交易所

    从SQLite数据库读取K线数据，模拟订单执行
    可以用于回测和本地虚拟盘测试
    """

    def __init__(
        self,
        db_path: str = None,
        table_name: str = None,
        api_key: str = "",
        api_secret: str = "",
        testnet: bool = False
    ):
        super().__init__(api_key, api_secret, testnet)
        self.logger = get_logger('exchange_layer.mock')

        # 数据库配置
        self.db_path = db_path or config.HIST_DB_PATH
        self.table_name = table_name or config.HIST_TABLE

        # 模拟账户
        self.initial_balance = 10000.0  # 初始USDT余额
        self.balance = self.initial_balance
        self.positions = {}  # symbol -> position_info

        # 订单存储
        self.orders = {}  # order_id -> Order
        # 使用时间戳作为起始ID，避免重启后ID冲突
        self.order_counter = int(datetime.now().timestamp() * 1000)

        # K线缓存
        self.klines_cache = {}  # (symbol, interval) -> [Kline]
        self.current_kline_index = {}  # (symbol, interval) -> index

        # 数据库连接
        self.conn: Optional[sqlite3.Connection] = None
        
        # 本地订单管理器
        self.local_order_manager = LocalOrderManager()

    def connect(self) -> bool:
        """连接到数据库"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row

            # 测试查询
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")
            count = cursor.fetchone()[0]

            self.connected = True
            self.logger.info(f"✓ 本地模拟交易所连接成功")
            self.logger.info(f"  数据库: {self.db_path}")
            self.logger.info(f"  数据表: {self.table_name}")
            self.logger.info(f"  K线记录: {count}条")
            return True

        except Exception as e:
            self.logger.error(f"本地模拟交易所连接失败: {e}", exc_info=True)
            self.connected = False
            return False

    def disconnect(self):
        """断开连接"""
        if self.conn:
            self.conn.close()
            self.conn = None
        self.connected = False
        self.logger.info("已断开本地模拟交易所连接")

    def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 1000,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Kline]:
        """
        从数据库获取K线数据

        Args:
            symbol: 交易对 (如 BTCUSD_PERP)
            interval: 时间周期 (1m, 5m, 15m, 1h, 4h, 1d等)
            limit: 数量限制
            start_time: 开始时间
            end_time: 结束时间
        """
        conn = None
        try:
            # 每次查询创建新连接（避免线程问题）
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row

            # 构建SQL查询
            sql = f"""
                SELECT * FROM {self.table_name}
                WHERE 1=1
            """
            params = []

            if start_time:
                sql += " AND open_time >= ?"
                params.append(start_time.strftime('%Y-%m-%dT%H:%M:%S'))

            if end_time:
                sql += " AND open_time <= ?"
                params.append(end_time.strftime('%Y-%m-%dT%H:%M:%S'))

            sql += " ORDER BY open_time ASC LIMIT ?"
            params.append(limit)

            self.logger.debug(f"查询K线: {symbol} {interval} limit={limit}")

            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()

            result = []
            for row in rows:
                # 处理时间格式：支持多种格式
                open_time_str = row['open_time']
                if 'T' in open_time_str:
                    # ISO格式: 2023-01-01T00:00:00
                    open_time = datetime.fromisoformat(open_time_str)
                else:
                    # 传统格式: 2023-01-01 00:00:00
                    open_time = datetime.strptime(open_time_str, '%Y-%m-%d %H:%M:%S')

                close_time = None
                close_time_val = row['close_time'] if 'close_time' in row.keys() else None
                if close_time_val:
                    close_time_str = close_time_val
                    if 'T' in close_time_str:
                        close_time = datetime.fromisoformat(close_time_str)
                    else:
                        close_time = datetime.strptime(close_time_str, '%Y-%m-%d %H:%M:%S')

                result.append(Kline(
                    symbol=symbol,
                    interval=interval,
                    open_time=open_time,
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=float(row['volume']),
                    close_time=close_time,
                ))

            self.logger.debug(f"获取到 {len(result)} 条K线")
            return result

        except Exception as e:
            self.logger.error(f"获取K线失败: {e}", exc_info=True)
            return []
        finally:
            if conn:
                conn.close()

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        client_order_id: Optional[str] = None,
        current_time: Optional[datetime] = None,
        **kwargs
    ) -> Order:
        """
        下单（模拟）

        市价单：基于当前K线时刻向后1分钟取收盘价成交
        限价单：直接按下单价格成交（后台已判断可成交），或基于后续10条K线判断成交
        
        Args:
            current_time: 当前K线时间戳（下单时刻）
        """
        try:
            order_id = str(self.order_counter)
            self.order_counter += 1

            if not client_order_id:
                client_order_id = f"mock_{uuid.uuid4().hex[:8]}"

            # 创建订单
            order = Order(
                order_id=order_id,
                client_order_id=client_order_id,
                symbol=symbol,
                side=OrderSide(side),
                type=OrderType(order_type),
                status=OrderStatus.NEW,
                price=price or 0,
                quantity=quantity,
                stop_price=stop_price,
            )

            # 保存订单（创建后立即保存到内存和本地数据库）
            self.orders[order_id] = order

            # 转换 side：BUY/SELL -> long/short
            side_map = {
                'BUY': 'long',
                'SELL': 'short',
                'buy': 'long',
                'sell': 'short',
                'LONG': 'long',
                'SHORT': 'short'
            }
            local_side = side_map.get(side, side)

            # 获取业务订单类型（默认为 OPEN）
            # 如果 kwargs 中有 business_order_type，使用它；否则根据上下文推断
            business_order_type = kwargs.get('business_order_type', 'OPEN')

            # 转换状态：NEW -> PENDING
            local_status = 'PENDING'  # 本地订单状态，不是交易所状态

            # 同步写入本地订单
            local_order = LocalOrder(
                order_id=order_id,
                trace_id=kwargs.get('trace_id', ''),
                side=local_side,
                order_type=business_order_type,  # 使用业务订单类型
                price=price or 0,
                contracts=quantity,
                status=local_status,
                kline_close_time=kwargs.get('kline_close_time')  # K线收盘时间
            )
            self.local_order_manager.create_order(local_order)

            # 市价单立即成交
            if order_type == 'MARKET':
                # 基于当前时刻向后1分钟查询K线，取收盘价作为成交价
                if current_time:
                    # 查询下一根K线（当前时刻 + 1分钟）
                    next_time = current_time + timedelta(minutes=1)
                    klines = self.get_klines(
                        symbol, '1m', limit=1,
                        start_time=next_time,
                        end_time=next_time + timedelta(seconds=59)
                    )
                    if klines:
                        execution_price = klines[0].close
                        self.logger.debug(
                            f"市价单使用下一根K线收盘价: {current_time} -> {next_time} @ {execution_price:.2f}"
                        )
                    else:
                        # 如果没有下一根K线，使用当前K线收盘价
                        klines = self.get_klines(
                            symbol, '1m', limit=1,
                            start_time=current_time,
                            end_time=current_time + timedelta(seconds=59)
                        )
                        execution_price = klines[0].close if klines else 43000.0
                        self.logger.warning(
                            f"无下一根K线，使用当前K线收盘价: {execution_price:.2f}"
                        )
                else:
                    # 兼容旧逻辑：没有传入时间戳时，使用最新K线
                    klines = self.get_klines(symbol, '1m', limit=1)
                    execution_price = klines[0].close if klines else 43000.0
                    self.logger.warning(
                        f"未传入current_time，使用最新K线: {execution_price:.2f}"
                    )

                # 更新订单为已成交
                order.status = OrderStatus.FILLED
                order.filled_quantity = quantity
                order.avg_price = execution_price
                order.update_time = datetime.now()

                # 同步更新本地订单状态（包含成交数量和成交价）
                self.local_order_manager.update_order_status(
                    order_id, 'FILLED',
                    filled_contracts=quantity,
                    avg_fill_price=execution_price
                )

                # 更新持仓和余额
                self._update_position(symbol, side, quantity, execution_price)

                self.logger.info(
                    f"✓ 市价单成交: {symbol} {side} "
                    f"数量={quantity} 价格={execution_price:.2f}"
                )
            elif order_type == 'LIMIT':
                # 限价单：如果传入了价格，直接按该价格成交（后台已判断可成交）
                if price and current_time:
                    # 直接按限价成交
                    execution_price = price
                    order.status = OrderStatus.FILLED
                    order.filled_quantity = quantity
                    order.avg_price = execution_price
                    order.update_time = datetime.now()

                    # 同步更新本地订单状态（包含成交数量和成交价）
                    self.local_order_manager.update_order_status(
                        order_id, 'FILLED',
                        filled_contracts=quantity,
                        avg_fill_price=execution_price
                    )
                    
                    # 更新持仓和余额
                    self._update_position(symbol, side, quantity, execution_price)
                    
                    self.logger.info(
                        f"✓ 限价单成交: {symbol} {side} "
                        f"数量={quantity} 价格={execution_price:.2f}"
                    )
                else:
                    # 兼容旧逻辑：基于后续10条K线判断是否成交
                    self.logger.info(
                        f"✓ 限价单已挂单: {symbol} {side} "
                        f"数量={quantity} 价格={price:.2f}"
                    )
                    # 检查成交（基于后续60条K线）
                    self._check_limit_order_fill(order, current_time, max_bars=60)
            else:
                # 其他订单类型进入订单簿
                self.logger.info(
                    f"✓ 订单已挂单: {symbol} {side} {order_type} "
                    f"数量={quantity} 价格={price:.2f}"
                )

            return order

        except Exception as e:
            self.logger.error(f"下单失败: {e}", exc_info=True)
            # 返回一个被拒绝的订单
            return Order(
                order_id='',
                client_order_id=client_order_id or '',
                symbol=symbol,
                side=OrderSide(side),
                type=OrderType(order_type),
                status=OrderStatus.REJECTED,
                price=price or 0,
                quantity=quantity,
            )

    def _check_limit_order_fill(self, order: Order, current_time: Optional[datetime] = None, max_bars: int = 60):
        """
        检查限价单是否成交（基于后续K线）

        逻辑：
        1. 使用传入的current_time或获取当前最新K线的时间戳
        2. 获取后续的10条1分钟K线
        3. 逐条判断价格是否在高低价范围内
        4. 如果满足条件，更新订单状态为成交
        5. 如果10条内都不成交，标记为失败（EXPIRED）

        Args:
            order: 订单对象
            current_time: 下单时刻的时间戳
            max_bars: 最多检查的K线数量，默认10条
        """
        try:
            # 获取当前时间
            if not current_time:
                # 获取当前最新K线（下单时刻的K线）
                current_klines = self.get_klines(order.symbol, '1m', limit=1)
                if not current_klines:
                    self.logger.warning(f"无法获取当前K线数据，订单 {order.order_id} 暂不处理")
                    return
                current_time = current_klines[0].open_time

            # 获取后续的max_bars条K线
            # 注意：这里我们需要获取比当前时间更晚的K线
            # 计算结束时间：当前时间 + max_bars分钟
            from datetime import timedelta
            end_time = current_time + timedelta(minutes=max_bars)

            # 获取后续K线
            future_klines = self.get_klines(
                order.symbol,
                '1m',
                limit=max_bars + 10,  # 多取一些以确保有足够的后续数据
                start_time=current_time + timedelta(seconds=1),  # 从下一秒开始
                end_time=end_time
            )

            if not future_klines:
                # 如果没有后续K线，说明到了数据末尾，保持挂单状态
                self.logger.debug(
                    f"无后续K线数据，订单 {order.order_id} 保持挂单状态"
                )
                return

            # 只取前max_bars条
            future_klines = future_klines[:max_bars]

            # 逐条K线检查是否成交
            for i, kline in enumerate(future_klines, 1):
                order_price = order.price
                filled = False
                execution_price = order_price

                if order.side == OrderSide.BUY:
                    # 买单：如果订单价格 >= 该K线的最低价，可以成交
                    if order_price >= kline.low:
                        filled = True
                        # 成交价为订单价格和K线收盘价的较小值
                        execution_price = min(order_price, kline.close)
                        break  # 成交了，退出循环
                else:  # SELL
                    # 卖单：如果订单价格 <= 该K线的最高价，可以成交
                    if order_price <= kline.high:
                        filled = True
                        # 成交价为订单价格和K线收盘价的较大值
                        execution_price = max(order_price, kline.close)
                        break  # 成交了，退出循环

                self.logger.debug(
                    f"订单 {order.order_id} 检查第{i}条K线: "
                    f"高低价={kline.low:.2f}-{kline.high:.2f}, "
                    f"订单价={order_price:.2f}, "
                    f"未成交"
                )

            if filled:
                # 更新订单为已成交
                order.status = OrderStatus.FILLED
                order.filled_quantity = order.quantity
                order.avg_price = execution_price
                order.update_time = datetime.now()

                # 同步更新本地订单状态（包含成交数量和成交价）
                self.local_order_manager.update_order_status(
                    order.order_id, 'FILLED',
                    filled_contracts=order.quantity,
                    avg_fill_price=execution_price
                )

                # 更新持仓和余额
                self._update_position(
                    order.symbol,
                    order.side.value,
                    order.quantity,
                    execution_price
                )

                self.logger.info(
                    f"✓ 限价单成交: {order.symbol} {order.side.value} "
                    f"订单ID={order.order_id} "
                    f"数量={order.quantity} 价格={execution_price:.2f} "
                    f"(检查了{i}条K线后成交)"
                )
            else:
                # max_bars条K线内都没有成交，保持挂单状态（不标记为失败）
                # 订单将持续有效，直到价格触发或被主动取消

                self.logger.info(
                    f"✓ 限价单保持挂单: {order.symbol} {order.side.value} "
                    f"订单ID={order.order_id} "
                    f"价格={order_price:.2f} "
                    f"(检查了{max_bars}条K线后未成交，订单继续有效)"
                )

        except Exception as e:
            self.logger.error(f"检查订单成交失败: {e}", exc_info=True)

    def _update_position(self, symbol: str, side: str, quantity: float, price: float):
        """更新持仓"""
        if symbol not in self.positions:
            self.positions[symbol] = {
                'long_qty': 0,
                'short_qty': 0,
                'long_entry_price': 0,
                'short_entry_price': 0,
            }

        pos = self.positions[symbol]

        if side == 'BUY':
            # 多头开仓
            pos['long_qty'] += quantity
            if pos['long_qty'] > 0:
                # 更新平均入场价
                total_cost = pos['long_entry_price'] * (pos['long_qty'] - quantity) + price * quantity
                pos['long_entry_price'] = total_cost / pos['long_qty']
        else:
            # 空头开仓
            pos['short_qty'] += quantity
            if pos['short_qty'] > 0:
                total_cost = pos['short_entry_price'] * (pos['short_qty'] - quantity) + price * quantity
                pos['short_entry_price'] = total_cost / pos['short_qty']

        self.logger.debug(f"更新持仓: {symbol} {pos}")

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """取消订单"""
        try:
            if order_id in self.orders:
                order = self.orders[order_id]
                if order.status in [OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED]:
                    order.status = OrderStatus.CANCELED
                    order.update_time = datetime.now()
                    
                    # 同步更新本地订单状态
                    self.local_order_manager.update_order_status(order_id, 'CANCELED')
                    
                    self.logger.info(f"✓ 订单已取消: {order_id}")
                    return True
                else:
                    self.logger.warning(f"订单无法取消: {order_id} 状态={order.status.value}")
                    return False
            else:
                self.logger.warning(f"订单不存在: {order_id}")
                return False
        except Exception as e:
            self.logger.error(f"取消订单失败: {e}", exc_info=True)
            return False

    def modify_order(
        self,
        symbol: str,
        order_id: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None
    ) -> bool:
        """
        修改订单

        Args:
            symbol: 交易对
            order_id: 订单ID
            quantity: 新数量（可选）
            price: 新价格（可选）

        Returns:
            bool: 是否修改成功
        """
        try:
            if order_id not in self.orders:
                self.logger.warning(f"订单不存在: {order_id}")
                return False

            order = self.orders[order_id]

            # 只能修改未成交的订单
            if order.status not in [OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED]:
                self.logger.warning(f"订单无法修改: {order_id} 状态={order.status.value}")
                return False

            # 记录修改前的值
            old_quantity = order.quantity
            old_price = order.price

            # 更新数量
            if quantity is not None:
                if quantity <= 0:
                    self.logger.error(f"无效的数量: {quantity}")
                    return False
                order.quantity = quantity

            # 更新价格
            if price is not None:
                if price <= 0:
                    self.logger.error(f"无效的价格: {price}")
                    return False
                order.price = price

            order.update_time = datetime.now()

            # 如果是限价单，重新检查成交
            if order.type == OrderType.LIMIT and price is not None:
                self._check_limit_order_fill(order)

            self.logger.info(
                f"✓ 订单已修改: {order_id} "
                f"数量: {old_quantity} -> {order.quantity if quantity else '不变'} "
                f"价格: {old_price:.2f} -> {order.price if price else '不变'}"
            )

            return True

        except Exception as e:
            self.logger.error(f"修改订单失败: {e}", exc_info=True)
            return False

    def cancel_all_orders(self, symbol: str) -> int:
        """取消所有订单"""
        count = 0
        for order_id, order in list(self.orders.items()):
            if order.symbol == symbol and order.status in [OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED]:
                if self.cancel_order(symbol, order_id):
                    count += 1
        return count

    def get_order(self, symbol: str, order_id: str) -> Optional[Order]:
        """查询订单"""
        return self.orders.get(order_id)

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """查询所有挂单"""
        open_orders = []
        for order in self.orders.values():
            if order.status in [OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED]:
                if symbol is None or order.symbol == symbol:
                    open_orders.append(order)
        return open_orders

    def get_account_info(self, asset: str = 'BTC') -> AccountInfo:
        """获取账户信息（从数据库读取已实现盈亏，asset 参数仅用于接口兼容）"""
        # 从数据库读取最新的已实现盈亏
        realized_pnl = self._get_realized_pnl_from_db()
        
        # 计算未实现盈亏（基于当前持仓）
        unrealized_pnl = 0.0
        for symbol, pos in self.positions.items():
            if pos['long_qty'] > 0:
                # 获取最新价格
                klines = self.get_klines(symbol, '1m', limit=1)
                if klines:
                    current_price = klines[0].close
                    unrealized_pnl += (current_price - pos['long_entry_price']) * pos['long_qty']
            elif pos['short_qty'] > 0:
                klines = self.get_klines(symbol, '1m', limit=1)
                if klines:
                    current_price = klines[0].close
                    unrealized_pnl += (pos['short_entry_price'] - current_price) * pos['short_qty']
        
        # 总余额 = 初始余额 + 已实现盈亏
        total_balance = self.initial_balance + realized_pnl
        available_balance = total_balance + unrealized_pnl

        return AccountInfo(
            total_wallet_balance=total_balance,
            available_balance=available_balance,
            unrealized_pnl=unrealized_pnl,
        )

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取持仓信息（计算实际未实现盈亏）"""
        if symbol in self.positions:
            pos = self.positions[symbol]
            
            # 获取当前价格
            klines = self.get_klines(symbol, '1m', limit=1)
            current_price = klines[0].close if klines else 0.0
            
            if pos['long_qty'] > 0:
                # 多头未实现盈亏 = (当前价 - 入场价) * 数量
                unrealized_pnl = (current_price - pos['long_entry_price']) * pos['long_qty'] if current_price > 0 else 0.0
                return {
                    'symbol': symbol,
                    'position_amount': pos['long_qty'],
                    'entry_price': pos['long_entry_price'],
                    'unrealized_pnl': unrealized_pnl,
                    'leverage': 1,
                    'side': 'LONG',
                }
            elif pos['short_qty'] > 0:
                # 空头未实现盈亏 = (入场价 - 当前价) * 数量
                unrealized_pnl = (pos['short_entry_price'] - current_price) * pos['short_qty'] if current_price > 0 else 0.0
                return {
                    'symbol': symbol,
                    'position_amount': pos['short_qty'],
                    'entry_price': pos['short_entry_price'],
                    'unrealized_pnl': unrealized_pnl,
                    'leverage': 1,
                    'side': 'SHORT',
                }
        return None

    def _get_realized_pnl_from_db(self) -> float:
        """从数据库读取最新的已实现盈亏"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 尝试从 sim_log 表读取最新的 realized_pnl
            cursor.execute("""
                SELECT realized_pnl 
                FROM sim_log 
                WHERE realized_pnl IS NOT NULL 
                ORDER BY id DESC 
                LIMIT 1
            """)
            row = cursor.fetchone()
            
            if row and row[0] is not None:
                return float(row[0])
            
            # 如果 sim_log 没有，尝试从 backtestlog 读取
            cursor.execute("""
                SELECT realized_pnl 
                FROM backtestlog 
                WHERE realized_pnl IS NOT NULL 
                ORDER BY id DESC 
                LIMIT 1
            """)
            row = cursor.fetchone()
            
            if row and row[0] is not None:
                return float(row[0])
            
            # 如果都没有，返回 0
            return 0.0
            
        except Exception as e:
            self.logger.debug(f"读取已实现盈亏失败: {e}")
            return 0.0
        finally:
            if conn:
                conn.close()

    def reset_account(self):
        """重置账户（用于新回测）"""
        self.balance = self.initial_balance
        self.positions.clear()
        self.orders.clear()
        self.order_counter = 1000
        self.logger.info("账户已重置")
