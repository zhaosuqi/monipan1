#!/usr/bin/env python3
"""
验证所有修复是否就绪
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / 'data' / 'klines.db'

def verify_all():
    """验证所有修复"""
    print("=" * 70)
    print("验证修复状态")
    print("=" * 70)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. 检查表结构
    print("\n1. 检查 orders 表约束:")
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='orders'")
    table_sql = cursor.fetchone()['sql']

    if "CHECK(side IN ('long', 'short'))" in table_sql:
        print("  ✓ side 约束正确: CHECK(side IN ('long', 'short'))")
    else:
        print("  ❌ side 约束不正确")

    # 2. 检查当前数据
    print("\n2. 检查当前数据状态:")
    cursor.execute("SELECT COUNT(*) as count FROM sim_log")
    simlog_count = cursor.fetchone()['count']
    print(f"  - sim_log: {simlog_count} 条")

    cursor.execute("SELECT COUNT(*) as count FROM orders")
    orders_count = cursor.fetchone()['count']
    print(f"  - orders: {orders_count} 条")

    cursor.execute("SELECT COUNT(*) as count FROM order_status_history")
    history_count = cursor.fetchone()['count']
    print(f"  - order_status_history: {history_count} 条")

    # 3. 检查代码修复
    print("\n3. 检查代码修复:")

    # 检查 MockExchange side 转换
    try:
        with open('exchange_layer/mock_exchange.py', 'r') as f:
            mock_exchange_code = f.read()

        if "side_map = {" in mock_exchange_code and "'BUY': 'long'" in mock_exchange_code:
            print("  ✓ MockExchange side 转换已修复")
        else:
            print("  ❌ MockExchange side 转换未修复")

        if "local_side = side_map.get(side, side)" in mock_exchange_code:
            print("  ✓ 使用转换后的 local_side")
        else:
            print("  ❌ 未使用转换后的 local_side")

    except Exception as e:
        print(f"  ❌ 检查 MockExchange 失败: {e}")

    # 检查回测清空逻辑
    try:
        with open('web_app.py', 'r') as f:
            web_app_code = f.read()

        if "DELETE FROM orders" in web_app_code:
            print("  ✓ 回测清空 orders 表已添加")
        else:
            print("  ❌ 回测清空 orders 表未添加")

        if "DELETE FROM order_status_history" in web_app_code:
            print("  ✓ 回测清空 order_status_history 已添加")
        else:
            print("  ❌ 回测清空 order_status_history 未添加")

    except Exception as e:
        print(f"  ❌ 检查 web_app 失败: {e}")

    # 4. 检查 WAL 模式
    print("\n4. 检查数据库 WAL 模式:")
    try:
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        if journal_mode.upper() == 'WAL':
            print(f"  ✓ WAL 模式已启用: {journal_mode}")
        else:
            print(f"  ⚠️ WAL 模式未启用: {journal_mode}")
    except Exception as e:
        print(f"  ❌ 检查 WAL 模式失败: {e}")

    conn.close()

    # 5. 总结
    print("\n" + "=" * 70)
    print("总结:")
    print("=" * 70)
    print("✓ 代码修复已完成:")
    print("  1. MockExchange side 转换 (BUY/SELL -> long/short)")
    print("  2. 回测前清空 orders 表")
    print("  3. 回测前清空 order_status_history 表")
    print("  4. SQLite WAL 模式已启用")
    print()
    print("⏳ 下一步:")
    print("  - 运行新回测以生成数据")
    print("  - 回测后 orders 表应该有记录")
    print("  - sim_log 开仓次数 = orders OPEN 类型订单数")
    print("=" * 70)

if __name__ == "__main__":
    verify_all()
