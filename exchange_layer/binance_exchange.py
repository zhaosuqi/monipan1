#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
币安交易所实现 - 支持实盘和测试网
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from binance.cm_futures import CMFutures
from binance.error import ParameterRequiredError

from core.logger import get_logger
from trade_module.local_order import LocalOrderManager
from trade_module.local_order import Order as LocalOrder

from .base_exchange import BaseExchange
from .models import (AccountInfo, Kline, Order, OrderSide, OrderStatus,
                     OrderType)


class BinanceExchange(BaseExchange):
    """
    币安交易所实现

    支持实盘和测试网，通过testnet参数控制
    """

    def __init__(self, api_key: str = "", api_secret: str = "", testnet: bool = False):
        super().__init__(api_key, api_secret, testnet)
        self.logger = get_logger('exchange_layer.binance')
        self.client: Optional[CMFutures] = None
        self.hedge_mode = False  # 是否为双向持仓模式
        
        # 本地订单管理器
        self.local_order_manager = LocalOrderManager()

    def connect(self) -> bool:
        """连接到币安交易所"""
        try:
            if self.testnet:
                # 测试网
                self.client = CMFutures(
                    key=self.api_key,
                    secret=self.api_secret
                )
                self.client.base_url = 'https://testnet.binancefuture.com'
                self.logger.info("连接到币安测试网")
            else:
                # 实盘
                self.client = CMFutures(
                    key=self.api_key,
                    secret=self.api_secret
                )
                self.logger.info("连接到币安实盘")

            # 测试连接
            self.client.exchange_info()
            
            # 获取持仓模式
            try:
                # 检查是否开启双向持仓
                # get_position_mode返回 {'dualSidePosition': True/False}
                pos_mode = self.client.get_position_mode()
                self.hedge_mode = pos_mode.get('dualSidePosition', False)
                mode_str = "双向持仓(Hedge Mode)" if self.hedge_mode else "单向持仓(One-Way Mode)"
                self.logger.info(f"持仓模式: {mode_str}")
            except Exception as e:
                self.logger.warning(f"获取持仓模式失败，默认使用单向持仓: {e}")
                self.hedge_mode = False

            self.connected = True
            self.logger.info("✓ 币安交易所连接成功")
            return True

        except Exception as e:
            self.logger.error(f"币安交易所连接失败: {e}", exc_info=True)
            self.connected = False
            return False

    def disconnect(self):
        """断开连接"""
        self.client = None
        self.connected = False
        self.logger.info("已断开币安交易所连接")

    def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 1000,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Kline]:
        """
        获取K线数据

        Args:
            symbol: 交易对 (如 BTCUSD_PERP)
            interval: 时间周期 (1m, 5m, 15m, 1h, 4h, 1d等)
            limit: 数量限制 (默认1000, 最大1000)
            start_time: 开始时间
            end_time: 结束时间
        """
        try:
            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': limit
            }

            if start_time:
                params['startTime'] = int(start_time.timestamp() * 1000)
            if end_time:
                params['endTime'] = int(end_time.timestamp() * 1000)

            # 打印请求参数
            self.logger.debug(
                f"获取K线参数: {symbol} {interval} limit={limit} "
                f"startTime={params.get('startTime')} ({start_time}) "
                f"endTime={params.get('endTime')} ({end_time})"
            )

            klines = self.client.klines(**params)

            result = []
            for kline in klines:
                # 币安API返回的是UTC时间戳，直接使用UTC时间
                utc_open_time = datetime.fromtimestamp(kline[0] / 1000, tz=timezone.utc)
                utc_close_time = datetime.fromtimestamp(kline[6] / 1000, tz=timezone.utc)

                result.append(Kline(
                    symbol=symbol,
                    interval=interval,
                    open_time=utc_open_time,
                    open=float(kline[1]),
                    high=float(kline[2]),
                    low=float(kline[3]),
                    close=float(kline[4]),
                    volume=float(kline[5]),
                    close_time=utc_close_time,
                    quote_volume=float(kline[7]),
                    trades=int(kline[8]),
                    taker_buy_base=float(kline[9]),
                    taker_buy_quote=float(kline[10]),
                ))

            # 打印返回K线的时间范围
            if result:
                self.logger.debug(
                    f"获取到 {len(result)} 条K线, "
                    f"时间范围: {result[0].open_time} ~ {result[-1].close_time}"
                )
            else:
                self.logger.debug(f"获取到 0 条K线")

            return result

        except Exception as e:
            self.logger.error(f"获取K线失败: {e}", exc_info=True)
            return []

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
        下单

        Args:
            symbol: 交易对
            side: 方向 (BUY/SELL)
            order_type: 订单类型 (MARKET/LIMIT/STOP_MARKET/STOP_LIMIT)
            quantity: 数量
            price: 价格 (限价单必需)
            stop_price: 止损价格 (止损单必需)
            client_order_id: 客户端订单ID
            current_time: 当前K线时间戳（真实交易所不使用此参数）
            **kwargs: 其他参数
        """
        try:
            params = {
                'symbol': symbol,
                'side': side,
                'type': order_type,
                'quantity': quantity,
            }

            if price:
                params['price'] = price
            if stop_price:
                params['stopPrice'] = stop_price
            if client_order_id:
                params['newClientOrderId'] = client_order_id

            # 处理双向持仓模式(Hedge Mode)的positionSide参数
            if self.hedge_mode and 'positionSide' not in params and 'positionSide' not in kwargs:
                # 只有当 params 中没有指定 positionSide 时才自动推断
                is_reduce_only = params.get('reduceOnly', False) or kwargs.get('reduceOnly', False)
                order_side = side.upper()
                
                if is_reduce_only:
                    # 减仓/平仓单
                    # BUY + ReduceOnly -> 平空 -> positionSide=SHORT
                    # SELL + ReduceOnly -> 平多 -> positionSide=LONG
                    if order_side == 'BUY':
                        params['positionSide'] = 'SHORT'
                    else:
                        params['positionSide'] = 'LONG'
                else:
                    # 开仓单 (或普通单)
                    # BUY -> 开多 -> positionSide=LONG
                    # SELL -> 开空 -> positionSide=SHORT
                    if order_side == 'BUY':
                        params['positionSide'] = 'LONG'
                    else:
                        params['positionSide'] = 'SHORT'
                
                self.logger.info(f"   [Hedge Mode] 自动补充 positionSide={params['positionSide']}")

            # 币安对限价/止损限价单必须提供 timeInForce
            limit_types = {
                'LIMIT', 'STOP', 'TAKE_PROFIT',
                'STOP_MARKET', 'STOP_LIMIT', 'TAKE_PROFIT_LIMIT'
            }
            if order_type.upper() in limit_types:
                params.setdefault('timeInForce', 'GTC')

            # 添加其他参数
            params.update(kwargs)

            # 记录API请求详情
            api_url = self.client.base_url
            self.logger.info(f"📤 [API请求] POST {api_url}/fapi/v1/order")
            self.logger.info(f"   下单参数: {symbol} {side} {order_type}")
            self.logger.info(f"   数量={quantity} 价格={price}")
            self.logger.debug(f"   完整参数: {params}")

            result = self.client.new_order(**params)
            # 记录币安返回的原始订单数据，便于排查字段差异
            self.logger.info(f"📥 [API原始响应] new_order: {result}")
            
            self.logger.info(f"📥 [API响应] 订单ID={result.get('orderId')} 状态={result.get('status')}")

            order = Order(
                order_id=str(result['orderId']),
                client_order_id=result.get('clientOrderId', ''),
                symbol=result['symbol'],
                side=OrderSide(result['side']),
                type=OrderType(result['type']),
                status=OrderStatus(result['status']),
                price=float(result.get('price', 0)),
                quantity=float(result['origQty']),
                filled_quantity=float(result.get('executedQty', 0)),
                avg_price=float(result.get('avgPrice', 0)),
                create_time=datetime.fromtimestamp(result['time'] / 1000) if result.get('time') else None,
            )

            # 若订单已成交，拉取成交明细获取精确成交均价与手续费
            if order.status == OrderStatus.FILLED:
                try:
                    trades = self.client.user_trades(
                        symbol=symbol,
                        orderId=int(order.order_id)
                    )
                    if trades:
                        qty_sum = sum(float(t.get('qty', 0)) for t in trades)
                        notional_sum = sum(
                            float(t.get('price', 0)) * float(t.get('qty', 0))
                            for t in trades
                        )
                        if qty_sum > 0:
                            order.avg_price = notional_sum / qty_sum

                        order.commission = sum(float(t.get('commission', 0)) for t in trades)
                        order.commission_asset = trades[0].get('commissionAsset', '') or ''

                        self.logger.info(
                            f"📊 [成交明细] 均价={order.avg_price:.6f} | "
                            f"手续费={order.commission} {order.commission_asset} | 成交笔数={len(trades)}"
                        )
                except Exception as fetch_err:
                    self.logger.warning(f"获取成交明细失败: {fetch_err}")
            
            # 转换 side：BUY/SELL -> long/short
            side_map = {
                'BUY': 'long',
                'SELL': 'short',
                'buy': 'long',
                'sell': 'short'
            }
            local_side = side_map.get(side, side.lower())
            
            # 获取业务订单类型
            business_order_type = kwargs.get('business_order_type', 'OPEN')
            
            # 状态映射: 适配本地数据库约束
            # DB允许: 'PENDING', 'FILLED', 'PARTIALLY_FILLED', 'CANCELED', 'EXPIRED'
            status_map = {
                'NEW': 'PENDING',
                'REJECTED': 'CANCELED',
                'PENDING_CANCEL': 'PENDING'
            }
            local_status = status_map.get(order.status.value, order.status.value)
            
            # 同步写入本地订单
            local_order = LocalOrder(
                order_id=order.order_id,
                trace_id=kwargs.get('trace_id', ''),
                side=local_side,
                order_type=business_order_type,
                price=order.price,
                contracts=quantity,
                status=local_status,
                kline_close_time=kwargs.get('kline_close_time')
            )
            self.local_order_manager.create_order(local_order)

            self.logger.info(f"✓ 下单成功 订单ID={order.order_id}")
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

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """取消订单"""
        try:
            api_url = self.client.base_url
            self.logger.info(f"📤 [API请求] DELETE {api_url}/fapi/v1/order")
            self.logger.info(f"   取消订单: {symbol} 订单ID={order_id}")
            result = self.client.cancel_order(symbol=symbol, orderId=int(order_id))
            self.logger.info(f"📥 [API原始响应] cancel_order: {result}")
            
            # 同步更新本地订单状态
            self.local_order_manager.update_order_status(order_id, 'CANCELED')
            
            self.logger.info("✓ 订单已取消")
            return True
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

        币安API不支持直接修改订单，需要先取消原订单，再创建新订单
        """
        try:
            # 1. 查询原订单
            original_order = self.get_order(symbol, order_id)
            if not original_order:
                self.logger.error(f"订单不存在: {order_id}")
                return False

            # 2. 取消原订单
            if not self.cancel_order(symbol, order_id):
                self.logger.error(f"无法取消原订单: {order_id}")
                return False

            # 3. 创建新订单（使用原订单的参数，只修改指定的字段）
            new_quantity = quantity if quantity is not None else original_order.quantity
            new_price = price if price is not None else original_order.price

            new_order = self.place_order(
                symbol=symbol,
                side=original_order.side.value,
                order_type=original_order.type.value,
                quantity=new_quantity,
                price=new_price,
                client_order_id=original_order.client_order_id,
            )

            return new_order.status != OrderStatus.REJECTED

        except Exception as e:
            self.logger.error(f"修改订单失败: {e}", exc_info=True)
            return False

    def cancel_all_orders(self, symbol: str) -> int:
        """取消所有订单"""
        try:
            api_url = self.client.base_url
            self.logger.info(f"📤 [API请求] DELETE {api_url}/fapi/v1/allOpenOrders")
            self.logger.info(f"   取消所有订单: {symbol}")
            result = self.client.cancel_open_orders(symbol=symbol)
            self.logger.info(f"📥 [API原始响应] cancel_open_orders: {result}")
            count = len(result) if isinstance(result, list) else 0
            self.logger.info(f"✓ 已取消 {count} 个订单")
            return count
        except Exception as e:
            self.logger.error(f"取消所有订单失败: {e}", exc_info=True)
            return 0

    def get_order(self, symbol: str, order_id: str) -> Optional[Order]:
        """查询订单（并同步本地订单状态）"""
        try:
            api_url = self.client.base_url
            self.logger.info(f"📤 [API请求] GET {api_url}/fapi/v1/order")
            self.logger.info(f"   查询订单: {symbol} 订单ID={order_id}")

            result = self.client.query_order(symbol=symbol, orderId=int(order_id))
            self.logger.info(f"📥 [API原始响应] query_order: {result}")

            order = Order.from_dict(result)
            
            # 同步本地订单状态（如果状态有变化）
            if order and order.status:
                # 状态映射: 适配本地数据库约束
                status_map = {
                    'NEW': 'PENDING',
                    'REJECTED': 'CANCELED',
                    'PENDING_CANCEL': 'PENDING'
                }
                local_status = status_map.get(order.status.value, order.status.value)
                self.local_order_manager.update_order_status(order_id, local_status)
            
            return order
        except Exception as e:
            self.logger.error(f"查询订单失败: {e}", exc_info=True)
            return None

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """查询所有挂单（CMFutures 库接口不稳定，直接用 sign_request）"""
        try:
            api_url = self.client.base_url
            if not symbol:
                symbol = config.SYMBOL

            self.logger.info(f"📤 [API请求] GET {api_url}/dapi/v1/openOrders")
            self.logger.info(f"   查询挂单: {symbol}")

            # 直接签名请求，绕过库的不稳定封装
            result = self.client.sign_request(
                "GET", "/dapi/v1/openOrders", {"symbol": symbol}
            )

            self.logger.info(f"📥 [API原始响应] get_open_orders: {result}")

            orders = []
            for item in result:
                orders.append(Order.from_dict(item))

            return orders
        except Exception as e:
            self.logger.error(f"查询挂单失败: {e}", exc_info=True)
            return []

    def get_account_info(self, asset: str = 'BTC') -> AccountInfo:
        """
        获取账户信息
        
        Args:
            asset: 资产类型，默认 BTC（币本位合约以 BTC 计价）
        """
        try:
            api_url = self.client.base_url
            self.logger.info(f"📤 [API请求] GET {api_url}/fapi/v1/account")
            
            result = self.client.account()

            # CM Futures API 的余额在 assets 数组中，而非顶级字段
            # 需要遍历 assets 找到指定资产的余额
            total_balance = 0.0
            available_balance = 0.0
            unrealized_pnl = 0.0
            
            assets = result.get('assets', [])
            for asset_info in assets:
                if asset_info.get('asset') == asset:
                    total_balance = float(asset_info.get('walletBalance', 0))
                    available_balance = float(asset_info.get('availableBalance', 0))
                    unrealized_pnl = float(asset_info.get('unrealizedProfit', 0))
                    break
            
            self.logger.info(
                f"📥 [API响应] {asset} 余额: 总计={total_balance:.8f} | "
                f"可用={available_balance:.8f} | "
                f"未实现盈亏={unrealized_pnl:.8f}"
            )

            return AccountInfo(
                total_wallet_balance=total_balance,
                available_balance=available_balance,
                unrealized_pnl=unrealized_pnl,
            )
        except Exception as e:
            self.logger.error(f"获取账户信息失败: {e}", exc_info=True)
            return AccountInfo(0, 0, 0)

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取持仓信息"""
        try:
            api_url = self.client.base_url
            self.logger.info(f"📤 [API请求] GET {api_url}/dapi/v1/positionRisk")
            self.logger.info(f"   查询持仓: {symbol}")

            positions = []
            # 兼容不同版本 python-binance 的 CMFutures 方法名
            if hasattr(self.client, 'position_information'):
                positions = self.client.position_information(symbol=symbol)
            elif hasattr(self.client, 'position_risk'):
                positions = self.client.position_risk(symbol=symbol)
            elif hasattr(self.client, 'get_position_risk'):
                positions = self.client.get_position_risk(symbol=symbol)
            else:
                raise AttributeError(
                    "CMFutures 缺少 position 信息查询接口(position_information/position_risk/get_position_risk)"
                )

            # 仅打印非零持仓，过滤掉 positionAmt=0 的记录
            non_zero_positions = [p for p in positions if float(p.get('positionAmt', 0) or 0) != 0]
            self.logger.debug(
                f"📥 [API响应] 收到 {len(positions)} 条持仓记录，其中非零={len(non_zero_positions)}"
            )
            for idx, pos in enumerate(non_zero_positions):
                self.logger.info(f"持仓#{idx+1}: {pos}")

            for pos in non_zero_positions:
                pos_amt = float(pos.get('positionAmt', 0))
                return {
                    'symbol': pos.get('symbol', symbol),
                    'position_amount': pos_amt,
                    'entry_price': float(pos.get('entryPrice', 0)),
                    'unrealized_pnl': float(pos.get('unRealizedProfit', 0)),
                    'leverage': int(pos.get('leverage', 1)),
                    'side': 'LONG' if pos_amt > 0 else 'SHORT',
                }

            return None
        except Exception as e:
            self.logger.error(f"获取持仓信息失败: {e}", exc_info=True)
            return None

    def get_user_trades(self, symbol: str, order_id: Optional[int] = None, limit: int = 500) -> List[Dict[str, Any]]:
        """
        拉取用户成交明细（user_trades）

        Args:
            symbol: 交易对
            order_id: 可选，按 orderId 查询
            limit: 最大条数

        Returns:
            成交字典列表
        """
        try:
            if not self.client:
                return []

            if order_id is not None:
                trades = self.client.user_trades(symbol=symbol, orderId=int(order_id))
            else:
                try:
                    trades = self.client.user_trades(symbol=symbol, limit=limit)
                except TypeError:
                    trades = self.client.user_trades(symbol=symbol)

            self.logger.info(f"📥 [API原始响应] user_trades: len={len(trades) if trades else 0}")
            return trades or []
        except Exception as e:
            self.logger.warning(f"获取 user_trades 失败: {e}")
            return []
