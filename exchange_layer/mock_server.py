#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地虚拟币安API服务器

模拟币安API接口，提供HTTP服务
外部工具可以通过切换BASE_URL连接到此服务
"""

import json
from datetime import datetime
from typing import Dict, Any
from flask import Flask, request, jsonify

from .mock_exchange import MockExchange
from core.logger import get_logger


class MockBinanceServer:
    """
    本地虚拟币安API服务器

    提供与币安API兼容的HTTP接口
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        db_path: str = None,
        table_name: str = None
    ):
        self.logger = get_logger('exchange_layer.mock_server')
        self.host = host
        self.port = port

        # 创建模拟交易所
        self.exchange = MockExchange(
            db_path=db_path,
            table_name=table_name
        )

        # 创建Flask应用
        self.app = Flask(__name__)
        self._setup_routes()

        self.server_running = False

    def _setup_routes(self):
        """设置路由"""

        @self.app.route('/fapi/v1/klines', methods=['GET'])
        def get_klines():
            """获取K线数据 - 兼容币安API"""
            try:
                symbol = request.args.get('symbol', 'BTCUSD_PERP')
                interval = request.args.get('interval', '1m')
                limit = int(request.args.get('limit', 1000))
                start_time = request.args.get('startTime')
                end_time = request.args.get('endTime')

                # 转换时间戳
                start_dt = datetime.fromtimestamp(int(start_time) / 1000) if start_time else None
                end_dt = datetime.fromtimestamp(int(end_time) / 1000) if end_time else None

                # 获取K线
                klines = self.exchange.get_klines(
                    symbol=symbol,
                    interval=interval,
                    limit=limit,
                    start_time=start_dt,
                    end_time=end_dt
                )

                # 转换为币安API格式
                result = []
                for kline in klines:
                    result.append([
                        int(kline.open_time.timestamp() * 1000),
                        kline.open,
                        kline.high,
                        kline.low,
                        kline.close,
                        kline.volume,
                        int(kline.close_time.timestamp() * 1000) if kline.close_time else 0,
                        kline.quote_volume,
                        kline.trades,
                        kline.taker_buy_base,
                        kline.taker_buy_quote,
                        0,
                    ])

                return jsonify(result)

            except Exception as e:
                self.logger.error(f"获取K线失败: {e}", exc_info=True)
                return jsonify({'error': str(e)}), 500

        @self.app.route('/fapi/v1/order', methods=['POST'])
        def place_order():
            """下单 - 兼容币安API"""
            try:
                data = request.get_json()

                order = self.exchange.place_order(
                    symbol=data.get('symbol', 'BTCUSD_PERP'),
                    side=data.get('side', 'BUY'),
                    order_type=data.get('type', 'MARKET'),
                    quantity=float(data.get('quantity', 0)),
                    price=float(data.get('price', 0)) if data.get('price') else None,
                    stop_price=float(data.get('stopPrice', 0)) if data.get('stopPrice') else None,
                    client_order_id=data.get('newClientOrderId'),
                )

                return jsonify(order.to_dict())

            except Exception as e:
                self.logger.error(f"下单失败: {e}", exc_info=True)
                return jsonify({'error': str(e)}), 500

        @self.app.route('/fapi/v1/order', methods=['DELETE'])
        def cancel_order():
            """取消订单 - 兼容币安API"""
            try:
                symbol = request.args.get('symbol', 'BTCUSD_PERP')
                order_id = request.args.get('orderId')

                success = self.exchange.cancel_order(symbol, order_id)

                if success:
                    return jsonify({'symbol': symbol, 'orderId': order_id, 'status': 'CANCELED'})
                else:
                    return jsonify({'error': 'Cancel failed'}), 400

            except Exception as e:
                self.logger.error(f"取消订单失败: {e}", exc_info=True)
                return jsonify({'error': str(e)}), 500

        @self.app.route('/fapi/v1/order', methods=['PUT'])
        def modify_order():
            """修改订单 - 兼容币安API"""
            try:
                data = request.get_json()
                symbol = data.get('symbol', 'BTCUSD_PERP')
                order_id = data.get('orderId')
                quantity = data.get('quantity')
                price = data.get('price')

                success = self.exchange.modify_order(
                    symbol=symbol,
                    order_id=order_id,
                    quantity=quantity,
                    price=price
                )

                if success:
                    # 查询更新后的订单
                    updated_order = self.exchange.get_order(symbol, order_id)
                    return jsonify(updated_order.to_dict())
                else:
                    return jsonify({'error': 'Modify failed'}), 400

            except Exception as e:
                self.logger.error(f"修改订单失败: {e}", exc_info=True)
                return jsonify({'error': str(e)}), 500

        @self.app.route('/fapi/v1/allOpenOrders', methods=['DELETE'])
        def cancel_all_orders():
            """取消所有订单 - 兼容币安API"""
            try:
                symbol = request.args.get('symbol', 'BTCUSD_PERP')
                count = self.exchange.cancel_all_orders(symbol)

                return jsonify({'count': count})

            except Exception as e:
                self.logger.error(f"取消所有订单失败: {e}", exc_info=True)
                return jsonify({'error': str(e)}), 500

        @self.app.route('/fapi/v1/order', methods=['GET'])
        def get_order():
            """查询订单 - 兼容币安API"""
            try:
                symbol = request.args.get('symbol', 'BTCUSD_PERP')
                order_id = request.args.get('orderId')

                order = self.exchange.get_order(symbol, order_id)

                if order:
                    return jsonify(order.to_dict())
                else:
                    return jsonify({'error': 'Order not found'}), 404

            except Exception as e:
                self.logger.error(f"查询订单失败: {e}", exc_info=True)
                return jsonify({'error': str(e)}), 500

        @self.app.route('/fapi/v1/openOrders', methods=['GET'])
        def get_open_orders():
            """查询所有挂单 - 兼容币安API"""
            try:
                symbol = request.args.get('symbol')

                orders = self.exchange.get_open_orders(symbol)

                result = [order.to_dict() for order in orders]
                return jsonify(result)

            except Exception as e:
                self.logger.error(f"查询挂单失败: {e}", exc_info=True)
                return jsonify({'error': str(e)}), 500

        @self.app.route('/fapi/v2/account', methods=['GET'])
        def get_account():
            """获取账户信息 - 兼容币安API"""
            try:
                account = self.exchange.get_account_info()

                return jsonify({
                    'totalWalletBalance': account.total_wallet_balance,
                    'availableBalance': account.available_balance,
                    'totalUnrealizedProfit': account.unrealized_pnl,
                })

            except Exception as e:
                self.logger.error(f"获取账户信息失败: {e}", exc_info=True)
                return jsonify({'error': str(e)}), 500

        @self.app.route('/fapi/v2/positionRisk', methods=['GET'])
        def get_position():
            """获取持仓信息 - 兼容币安API"""
            try:
                symbol = request.args.get('symbol')

                positions = []

                if symbol:
                    pos = self.exchange.get_position(symbol)
                    if pos:
                        positions.append({
                            'symbol': pos['symbol'],
                            'positionAmt': pos['position_amount'],
                            'entryPrice': pos['entry_price'],
                            'unRealizedProfit': pos['unrealized_pnl'],
                            'leverage': pos['leverage'],
                        })
                else:
                    # 返回所有持仓
                    # 简化版，只返回请求的symbol
                    pass

                return jsonify(positions)

            except Exception as e:
                self.logger.error(f"获取持仓信息失败: {e}", exc_info=True)
                return jsonify({'error': str(e)}), 500

        @self.app.route('/fapi/v1/exchangeInfo', methods=['GET'])
        def get_exchange_info():
            """获取交易所信息 - 兼容币安API"""
            return jsonify({
                'timezone': 'UTC',
                'serverTime': int(datetime.now().timestamp() * 1000),
                'exchangeFilters': [],
                'symbols': [
                    {
                        'symbol': 'BTCUSD_PERP',
                        'status': 'TRADING',
                        'contractType': 'PERPETUAL',
                        'baseAsset': 'BTC',
                        'quoteAsset': 'USD',
                    }
                ]
            })

        @self.app.route('/health', methods=['GET'])
        def health_check():
            """健康检查"""
            return jsonify({
                'status': 'ok',
                'exchange': 'mock_binance_server',
                'connected': self.exchange.is_connected(),
            })

    def start(self):
        """启动服务器"""
        if not self.exchange.connect():
            self.logger.error("无法连接到数据库，服务器启动失败")
            return

        self.logger.info("=" * 60)
        self.logger.info("启动本地虚拟币安API服务器")
        self.logger.info(f"监听地址: http://{self.host}:{self.port}")
        self.logger.info("K线接口: http://{}:{}/fapi/v1/klines".format(self.host, self.port))
        self.logger.info("下单接口: http://{}:{}/fapi/v1/order".format(self.host, self.port))
        self.logger.info("=" * 60)

        self.server_running = True
        self.app.run(host=self.host, port=self.port, debug=False)

    def stop(self):
        """停止服务器"""
        self.server_running = False
        self.exchange.disconnect()
        self.logger.info("本地虚拟币安API服务器已停止")


def main():
    """主函数 - 启动服务器"""
    import argparse

    parser = argparse.ArgumentParser(description='本地虚拟币安API服务器')
    parser.add_argument('--host', type=str, default='127.0.0.1', help='监听地址')
    parser.add_argument('--port', type=int, default=8080, help='监听端口')
    parser.add_argument('--db-path', type=str, help='数据库路径')
    parser.add_argument('--table', type=str, help='数据表名')

    args = parser.parse_args()

    server = MockBinanceServer(
        host=args.host,
        port=args.port,
        db_path=args.db_path,
        table_name=args.table
    )

    try:
        server.start()
    except KeyboardInterrupt:
        print("\n收到停止信号，正在关闭服务器...")
        server.stop()


if __name__ == '__main__':
    main()
