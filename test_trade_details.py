#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试获取平仓订单的成交明细（手续费和实现盈亏）

此脚本用于测试 _get_order_trade_details 方法，
获取模拟盘最后的交易平仓记录，并打印输出成交明细参数。
"""

import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载 .env 文件
from dotenv import load_dotenv

load_dotenv()

# 强制使用测试网
os.environ['BINANCE_TESTNET'] = '1'
os.environ['EXCHANGE_TYPE'] = 'binance_testnet'

# 设置代理（如果需要）
# os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
# os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'

from core.config import config
from core.logger import get_logger
from exchange_layer import ExchangeType, create_exchange

logger = get_logger('test_trade_details')


def get_recent_trades(exchange, symbol: str, limit: int = 50):
    """
    获取最近的成交记录
    
    Args:
        exchange: 交易所实例
        symbol: 交易对
        limit: 获取数量
        
    Returns:
        list: 成交记录列表
    """
    try:
        trades = exchange.get_user_trades(symbol, order_id=None, limit=limit)
        return trades or []
    except Exception as e:
        logger.error(f"获取成交记录失败: {e}")
        return []


def analyze_trade_details(trade):
    """
    分析单条成交记录
    
    Args:
        trade: 成交记录字典
    """
    print("\n" + "=" * 60)
    print(f"📋 成交ID: {trade.get('id', 'N/A')}")
    print(f"📋 订单ID: {trade.get('orderId', 'N/A')}")
    print("-" * 60)
    
    # 基本信息
    symbol = trade.get('symbol', 'N/A')
    side = trade.get('side', 'N/A')
    price = float(trade.get('price', 0) or 0)
    qty = float(trade.get('qty', 0) or 0)
    
    print(f"   交易对: {symbol}")
    print(f"   方向: {side}")
    print(f"   价格: {price:.2f}")
    print(f"   数量: {qty}")
    
    # 手续费信息
    commission = float(trade.get('commission', 0) or 0)
    commission_asset = trade.get('commissionAsset', '')
    
    print("-" * 60)
    print(f"💰 手续费: {commission:.8f} {commission_asset}")
    
    # 如果是 BTC 计价，转换为 USD
    if commission_asset.upper() == 'BTC' and price > 0:
        fee_usd = commission * price
        print(f"💰 手续费(USD估算): ${fee_usd:.4f}")
    
    # 实现盈亏
    realized_pnl = float(trade.get('realizedPnl', 0) or 0)
    print(f"💵 实现盈亏(USD): ${realized_pnl:.4f}")
    
    # 时间
    trade_time = trade.get('time', 'N/A')
    print(f"⏰ 成交时间: {trade_time}")
    
    # 买卖方向
    is_buyer = trade.get('buyer', trade.get('isBuyer', False))
    is_maker = trade.get('maker', trade.get('isMaker', False))
    print(f"   买方: {is_buyer} | 做市商: {is_maker}")
    
    print("=" * 60)


def group_trades_by_order(trades):
    """
    按订单ID分组成交记录
    
    Args:
        trades: 成交记录列表
        
    Returns:
        dict: {order_id: [trades]}
    """
    grouped = {}
    for trade in trades:
        order_id = trade.get('orderId')
        if order_id:
            if order_id not in grouped:
                grouped[order_id] = []
            grouped[order_id].append(trade)
    return grouped


def calculate_order_totals(trades_for_order):
    """
    计算订单的汇总数据（与 _get_order_trade_details 逻辑一致）
    
    Args:
        trades_for_order: 属于同一订单的成交记录列表
        
    Returns:
        dict: 汇总结果
    """
    total_commission = 0.0
    total_realized_pnl = 0.0
    commission_asset = None
    total_qty = 0.0
    
    for trade in trades_for_order:
        commission = float(trade.get('commission', 0) or 0)
        total_commission += commission
        
        realized_pnl = float(trade.get('realizedPnl', 0) or 0)
        total_realized_pnl += realized_pnl
        
        qty = float(trade.get('qty', 0) or 0)
        total_qty += qty
        
        if not commission_asset:
            commission_asset = trade.get('commissionAsset', '')
    
    # 获取平均价格用于转换
    avg_price = float(trades_for_order[0].get('price', 0) or 0) if trades_for_order else 0
    
    # 手续费转换为 USD（币本位合约 commission 是 BTC 计价）
    if commission_asset and commission_asset.upper() == 'BTC' and avg_price > 0:
        fee_usd = total_commission * avg_price
    else:
        fee_usd = total_commission
    
    # realizedPnl 也是 BTC 计价，需要转换为 USD
    # marginAsset 为 BTC 时，realizedPnl 单位是 BTC
    margin_asset = trades_for_order[0].get('marginAsset', '') if trades_for_order else ''
    if margin_asset.upper() == 'BTC' and avg_price > 0:
        pnl_usd = total_realized_pnl * avg_price
    else:
        pnl_usd = total_realized_pnl
    
    return {
        'real_fee_usd': fee_usd,
        'real_pnl_usd': pnl_usd,
        'real_pnl_btc': total_realized_pnl,  # 保留原始 BTC 值
        'commission_asset': commission_asset,
        'total_qty': total_qty,
        'trade_count': len(trades_for_order)
    }


def main():
    print("\n" + "=" * 70)
    print("🔍 测试获取平仓订单成交明细")
    print("=" * 70)
    
    # 显示当前配置（强制使用测试网）
    print(f"\n📡 当前模式: 测试网（强制）")
    print(f"📡 交易对: {config.SYMBOL}")
    print(f"📡 API Key: {config.BINANCE_TESTNET_API_KEY[:10] if config.BINANCE_TESTNET_API_KEY else 'N/A'}...")
    
    # 创建交易所连接（强制使用测试网）
    print("\n🔗 正在连接测试网交易所...")
    
    exchange = create_exchange(
        ExchangeType.BINANCE_TESTNET,
        api_key=config.BINANCE_TESTNET_API_KEY,
        api_secret=config.BINANCE_TESTNET_API_SECRET
    )
    
    if not exchange.connect():
        print("❌ 连接交易所失败")
        return
    
    print("✅ 交易所连接成功")
    
    # 获取最近的成交记录
    print(f"\n📥 正在获取最近 500 条成交记录...")
    trades = get_recent_trades(exchange, config.SYMBOL, limit=500)
    
    if not trades:
        print("❌ 没有找到成交记录")
        return
    
    print(f"✅ 获取到 {len(trades)} 条成交记录")
    
    # 打印第一条原始数据，查看完整字段
    if trades:
        print("\n📋 第一条成交记录原始数据:")
        import json
        print(json.dumps(trades[0], indent=2, default=str))
    
    # 按订单ID分组
    grouped = group_trades_by_order(trades)
    print(f"\n📊 共 {len(grouped)} 个订单")
    
    # 找出最后几笔平仓订单（realizedPnl != 0 的）
    print("\n" + "=" * 70)
    print("📊 最近的平仓订单（有实现盈亏的）")
    print("=" * 70)
    
    close_orders = []
    for order_id, order_trades in grouped.items():
        totals = calculate_order_totals(order_trades)
        # realizedPnl != 0 表示是平仓订单
        if abs(totals['real_pnl_usd']) > 0.0001:
            close_orders.append({
                'order_id': order_id,
                'trades': order_trades,
                'totals': totals
            })
    
    if not close_orders:
        print("\n⚠️ 没有找到平仓订单（所有订单的 realizedPnl 都为 0）")
        print("\n📋 显示最近的所有订单:")
        
        # 显示最近5个订单
        for i, (order_id, order_trades) in enumerate(list(grouped.items())[:5]):
            totals = calculate_order_totals(order_trades)
            print(f"\n订单 {i+1}: ID={order_id}")
            print(f"   成交笔数: {totals['trade_count']}")
            print(f"   总数量: {totals['total_qty']}")
            print(f"   手续费: ${totals['real_fee_usd']:.4f} ({totals['commission_asset']})")
            print(f"   实现盈亏: {totals['real_pnl_btc']:.10f} BTC ≈ ${totals['real_pnl_usd']:.4f}")
            
            # 显示原始成交记录
            for trade in order_trades[:2]:  # 最多显示2条
                analyze_trade_details(trade)
    else:
        print(f"\n✅ 找到 {len(close_orders)} 个平仓订单")
        
        # 显示最近3个平仓订单
        for i, close_order in enumerate(close_orders[:3]):
            order_id = close_order['order_id']
            totals = close_order['totals']
            
            print(f"\n{'='*70}")
            print(f"📋 平仓订单 {i+1}: ID={order_id}")
            print(f"{'='*70}")
            print(f"   成交笔数: {totals['trade_count']}")
            print(f"   总数量: {totals['total_qty']}")
            print(f"   💰 手续费: ${totals['real_fee_usd']:.6f} ({totals['commission_asset']})")
            print(f"   💵 实现盈亏: {totals['real_pnl_btc']:.10f} BTC ≈ ${totals['real_pnl_usd']:.4f}")
            
            # 这就是传递给飞书通知的数据
            print(f"\n   📤 飞书通知参数:")
            print(f"      real_fee_usd = {totals['real_fee_usd']:.6f}")
            print(f"      real_pnl_usd = {totals['real_pnl_usd']:.6f}")
            
            # 显示原始成交记录
            print(f"\n   原始成交明细:")
            for trade in close_order['trades']:
                analyze_trade_details(trade)
    
    print("\n" + "=" * 70)
    print("✅ 测试完成")
    print("=" * 70 + "\n")


if __name__ == '__main__':
    main()
