#!/usr/bin/env python3
"""
诊断 sim_log 问题
"""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / 'data' / 'klines.db'

def diagnose():
    """诊断 sim_log 问题"""
    print("=" * 70)
    print("SIM_LOG 诊断报告")
    print("=" * 70)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. 检查表是否存在
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='sim_log'
    """)
    table_exists = cursor.fetchone()

    if not table_exists:
        print("❌ sim_log 表不存在！")
        return

    print("✓ sim_log 表存在")

    # 2. 检查记录总数
    cursor.execute("SELECT COUNT(*) as count FROM sim_log")
    count = cursor.fetchone()['count']
    print(f"✓ 总记录数: {count}")

    if count == 0:
        print("\n⚠️ sim_log 表为空！")
        print("\n可能原因:")
        print("  1. 回测还未运行")
        print("  2. 回测开始时清空了数据，但还未完成")
        print("  3. 回测运行时数据写入失败（现在已修复 WAL 模式）")
        print("\n建议:")
        print("  - 运行一次回测，应该能正常写入数据")
        print("  - 检查回测日志是否有错误")
        return

    # 3. 检查数据时间范围
    cursor.execute("""
        SELECT
            MIN(log_time) as min_time,
            MAX(log_time) as max_time
        FROM sim_log
    """)
    time_range = cursor.fetchone()

    print(f"\n✓ 时间范围:")
    print(f"  最早: {time_range['min_time']}")
    print(f"  最晚: {time_range['max_time']}")

    # 4. 按事件类型统计
    cursor.execute("""
        SELECT
            event,
            COUNT(*) as count
        FROM sim_log
        GROUP BY event
        ORDER BY count DESC
    """)
    events = cursor.fetchall()

    print(f"\n✓ 事件类型统计:")
    for event in events:
        print(f"  - {event['event']}: {event['count']} 次")

    # 5. 检查最近的记录
    cursor.execute("""
        SELECT * FROM sim_log
        ORDER BY log_time DESC
        LIMIT 3
    """)
    recent = cursor.fetchall()

    print(f"\n✓ 最近 3 条记录:")
    for row in recent:
        print(f"  - {row['log_time']} | {row['event']} | "
              f"{row['side']} | {row['price']:.2f} | "
              f"盈亏: {row['pnl']:.6f}")

    # 6. 测试 API 逻辑
    print(f"\n✓ 测试 API 时间转换:")
    cursor.execute("""
        SELECT log_time, event, side, price, contracts, pnl
        FROM sim_log
        ORDER BY log_time ASC
        LIMIT 10
    """)
    rows = cursor.fetchall()

    markers_count = 0
    for row in rows:
        try:
            timestamp = row['log_time']
            dt = datetime.fromisoformat(timestamp.replace('+00:00', ''))
            time = int(dt.timestamp())
            markers_count += 1
        except:
            pass

    print(f"  - 可以转换为 API 标记: {markers_count} 条")

    # 7. 总结
    print("\n" + "=" * 70)
    if count > 0:
        print("✓ sim_log 表有数据")
        print(f"✓ API 应该能返回 {markers_count} 个标记（前10条测试）")
        print("\n如果页面看不到标记，请:")
        print("  1. 刷新浏览器页面（Ctrl+Shift+R 强制刷新）")
        print("  2. 检查浏览器控制台是否有错误")
        print("  3. 点击'刷新标记'按钮")
    else:
        print("⚠️ sim_log 表为空")
        print("\n建议运行一次回测生成数据")
    print("=" * 70)

    conn.close()

if __name__ == "__main__":
    diagnose()
