#!/usr/bin/env python3
"""
验证订单表结构和写入功能
"""
import sqlite3
from datetime import datetime
from pathlib import Path

# 数据库路径
DB_PATH = Path(__file__).parent / 'data' / 'klines.db'

def test_order_table():
    """测试订单表"""
    print("=" * 60)
    print("测试订单表结构")
    print("=" * 60)

    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=30.0,
        isolation_level=None
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")

    cursor = conn.cursor()

    # 检查表是否存在
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='orders'
    """)
    result = cursor.fetchone()

    if result:
        print("✓ orders 表存在")

        # 查看表结构
        cursor.execute("PRAGMA table_info(orders)")
        columns = cursor.fetchall()

        print("\n表结构:")
        for col in columns:
            print(f"  - {col[1]}: {col[2]}")

        # 插入测试数据
        test_order_id = f"TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        print(f"\n插入测试订单: {test_order_id}")

        try:
            cursor.execute("""
                INSERT INTO orders (
                    order_id, trace_id, symbol, side, order_type,
                    status, price, contracts, created_time, updated_time
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                test_order_id, 'test_trace', 'BTCUSD_PERP',
                'long', 'OPEN', 'PENDING', 95000.0, 10,
                datetime.now().isoformat(), datetime.now().isoformat()
            ))
            conn.commit()

            print("✓ 订单插入成功")

            # 查询验证
            cursor.execute(
                "SELECT * FROM orders WHERE order_id = ?",
                (test_order_id,)
            )
            result = cursor.fetchone()

            if result:
                print(f"✓ 订单已保存，DB ID: {result[0]}")
                print(f"  order_id: {result[1]}")
                print(f"  trace_id: {result[2]}")
                print(f"  side: {result[4]}")
                print(f"  order_type: {result[5]}")
                print(f"  price: {result[7]}")
                print(f"  contracts: {result[8]}")

                # 测试更新订单状态
                print("\n测试更新订单状态...")
                cursor.execute("""
                    UPDATE orders
                    SET status = ?, filled_contracts = ?, avg_fill_price = ?
                    WHERE order_id = ?
                """, ('FILLED', 10, 95050.0, test_order_id))
                conn.commit()

                print("✓ 订单状态更新成功")

                # 验证状态历史表
                cursor.execute("""
                    INSERT INTO order_status_history (
                        order_id, old_status, new_status, change_time
                    )
                    VALUES (?, ?, ?, ?)
                """, (test_order_id, 'PENDING', 'FILLED',
                      datetime.now().isoformat()))
                conn.commit()

                print("✓ 状态历史记录成功")

                # 清理测试数据
                cursor.execute(
                    "DELETE FROM orders WHERE order_id = ?",
                    (test_order_id,)
                )
                cursor.execute(
                    "DELETE FROM order_status_history WHERE order_id = ?",
                    (test_order_id,)
                )
                conn.commit()

                print("✓ 测试数据已清理")

                print("\n" + "=" * 60)
                print("✓✓✓ 所有测试通过！订单表工作正常 ✓✓✓")
                print("=" * 60)

            else:
                print("❌ 订单未找到")

        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()

    else:
        print("❌ orders 表不存在")

    conn.close()

if __name__ == "__main__":
    test_order_table()
