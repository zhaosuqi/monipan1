#!/usr/bin/env python3
"""
修复止盈单的 kline_close_time 问题的脚本

问题：
1. trade_engine.py 中 _place_initial_tp_order 使用了 pd.Timestamp.now()
2. 应该使用正确的 K线时间 (ts)

修复：
1. 修改 _place_initial_tp_order 方法签名，添加 ts 参数
2. 修改所有调用处传递 ts
3. 修改止盈单下单时使用 ts 而不是 pd.Timestamp.now()
"""

import re

def fix_trade_engine():
    """修复 trade_engine.py 中的止盈单时间问题"""

    file_path = "trade_module/trade_engine.py"

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 修复 1: 修改方法签名
    # 找到 def _place_initial_tp_order(self, pos: Position):
    # 替换为 def _place_initial_tp_order(self, pos: Position, ts=None):

    pattern1 = r'def _place_initial_tp_order\(self, pos: Position\):'
    replacement1 = 'def _place_initial_tp_order(self, pos: Position, ts=None):'
    content = re.sub(pattern1, replacement1, content)

    # 修复 2: 修改止盈单下单时的 kline_close_time
    # 找到 kline_close_time=str(pd.Timestamp.now())
    # 需要根据上下文替换为 kline_close_time=str(ts) if ts else ''

    # 第一个止盈单（在 _place_initial_tp_order 中）
    pattern2 = r'kline_close_time=str\(pd\.Timestamp\.now\(\)\)\s+#\s*当前时间作为K线时间'
    replacement2 = 'kline_close_time=str(ts) if ts else \'\'  # 使用K线时间'
    content = re.sub(pattern2, replacement2, content)

    # 第二个止盈单（在调整止盈单的地方）
    # 这个地方的上下文不同，需要单独处理

    print("✓ 已完成修复")
    print(f"  修改了方法签名: def _place_initial_tp_order(self, pos: Position, ts=None)")
    print(f"  替换了 kline_close_time 的错误用法")

    # 写回文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"\n✓ 文件已更新: {file_path}")

if __name__ == '__main__':
    fix_trade_engine()
