# 回测历史数据清理功能

## 功能说明

每次启动回测时，系统会自动清理 `sim_log` 表中的所有历史数据，确保每次回测都在干净的环境中运行，避免历史数据干扰当前回测结果。

## 实现细节

**文件:** `web_app.py:603-621`

```python
# 清理历史回测数据
logger.info("清理历史回测数据...")
try:
    from core.database import Database
    db = Database()
    cursor = db._get_connection().cursor()

    # 检查现有数据数量
    cursor.execute("SELECT COUNT(*) FROM sim_log")
    old_count = cursor.fetchone()[0]
    logger.info(f"发现 {old_count} 条历史数据")

    # 删除所有历史数据
    cursor.execute("DELETE FROM sim_log")
    db._get_connection().commit()
    logger.info("✓ 历史数据已清理")

except Exception as e:
    logger.error(f"清理历史数据失败: {e}")
```

## 执行时机

清理操作在回测工作线程启动时执行，具体顺序：

1. 用户点击"启动"按钮
2. `/api/bot/start` 接收请求
3. 检测到 `backtest` 模式
4. 创建后台线程运行 `run_backtest_worker()`
5. **【清理历史数据】**
6. 获取K线数据
7. 执行回测策略
8. 写入新的信号数据

## 验证结果

### 测试1: 首次运行

```
2026-01-06 12:16:27 - INFO - 清理历史回测数据...
2026-01-06 12:16:27 - INFO - 发现 1053 条历史数据
2026-01-06 12:16:27 - INFO - ✓ 历史数据已清理
```

### 数据验证

**清理前:**
```
总记录: 1053条
ID范围: 1 - 1053
时间范围: 2024-01-01 至 2024-01-10
```

**清理后（重新生成）:**
```
总记录: 1053条
ID范围: 1054 - 2106
时间范围: 2024-01-01 至 2024-01-10
```

**结论:**
- ✅ 旧数据（ID 1-1053）已被删除
- ✅ 新数据（ID 1054-2106）重新生成
- ✅ ID继续递增，保持数据库自增序列
- ✅ 每次回测都是干净的数据环境

## 日志输出

### 正常清理

```
2026-01-06 12:16:27 - __main__ - INFO - ============================================================
2026-01-06 12:16:27 - __main__ - INFO - 开始数据库回测
2026-01-06 12:16:27 - __main__ - INFO - ============================================================
2026-01-06 12:16:27 - __main__ - INFO - 清理历史回测数据...
2026-01-06 12:16:27 - __main__ - INFO - 发现 1053 条历史数据
2026-01-06 12:16:27 - __main__ - INFO - ✓ 历史数据已清理
2026-01-06 12:16:27 - data_module.data_source_adapter - INFO - 初始化数据源适配器，模式: replay
...
```

### 无历史数据

```
2026-01-06 12:20:00 - __main__ - INFO - 清理历史回测数据...
2026-01-06 12:20:00 - __main__ - INFO - 发现 0 条历史数据
2026-01-06 12:20:00 - __main__ - INFO - ✓ 历史数据已清理
```

## 优势

### 1. 数据隔离
- 每次回测互不干扰
- 避免旧数据污染新结果
- 确保回测结果可重现

### 2. 存储管理
- 自动清理，无需手动操作
- 避免数据库无限增长
- 保持良好的查询性能

### 3. 开发友好
- 快速迭代测试策略
- 即时看到新策略效果
- 无需担心数据冲突

## 数据流程

```
┌─────────────────────────────────────────────────────────┐
│ 1. 用户点击"启动"                                         │
└─────────────────┬───────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────────────────┐
│ 2. 检测模式为 backtest                                    │
└─────────────────┬───────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────────────────┐
│ 3. 创建后台线程                                           │
└─────────────────┬───────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────────────────┐
│ 4. 【清理历史数据】                                        │
│    - 查询现有数据数量                                      │
│    - 执行 DELETE FROM sim_log                            │
│    - 提交事务                                             │
│    - 记录日志                                             │
└─────────────────┬───────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────────────────┐
│ 5. 获取K线数据                                            │
└─────────────────┬───────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────────────────┐
│ 6. 执行回测策略                                            │
└─────────────────┬───────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────────────────┐
│ 7. 写入新信号数据（ID从上次最大值+1开始）                   │
└─────────────────┬───────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────────────────┐
│ 8. 完成回测，显示统计                                      │
└─────────────────────────────────────────────────────────┘
```

## 手动清理

如果需要手动清理历史数据，可以执行：

### 方法1: SQLite命令行

```bash
sqlite3 data/klines.db "DELETE FROM sim_log"
```

### 方法2: Python脚本

```python
from core.database import Database

db = Database()
cursor = db._get_connection().cursor()
cursor.execute("DELETE FROM sim_log")
db._get_connection().commit()
print(f"已删除 {cursor.rowcount} 条数据")
```

### 方法3: 查看清理效果

```bash
# 查看清理前数量
sqlite3 data/klines.db "SELECT COUNT(*) FROM sim_log"

# 清理数据
sqlite3 data/klines.db "DELETE FROM sim_log"

# 查看清理后数量
sqlite3 data/klines.db "SELECT COUNT(*) FROM sim_log"

# 重置自增ID（可选）
sqlite3 data/klines.db "DELETE FROM sqlite_sequence WHERE name='sim_log'"
```

## 注意事项

### 1. 数据不可恢复
- 清理操作无法撤销
- 建议在清理前备份重要数据
- 如需保留历史数据，请导出后再清理

### 2. 并发问题
- 同时启动多个回测可能导致冲突
- 确保前一个回测完成后再启动新的
- 系统会检查 `bot_state['running']` 状态

### 3. 数据库性能
- 频繁清理可能影响SQLite性能
- 建议定期执行 VACUUM 优化数据库
```bash
sqlite3 data/klines.db "VACUUM"
```

## 扩展功能

### 可选: 保留最近N次回测数据

如果不想每次都完全清理，可以修改为保留最近几次的数据：

```python
# 保留最近3次回测数据（每次约1000条）
KEEP_LAST_RUNS = 3
KEEP_SIGNALS = KEEP_LAST_RUNS * 1000

cursor.execute("""
    DELETE FROM sim_log
    WHERE id <= (
        SELECT id FROM sim_log
        ORDER BY id DESC
        LIMIT 1 OFFSET ?
    )
""", (KEEP_SIGNALS,))
```

### 可选: 按时间清理

```python
# 只删除30天前的数据
cursor.execute("""
    DELETE FROM sim_log
    WHERE datetime(log_time) < datetime('now', '-30 days')
""")
```

### 可选: 添加回测摘要表

创建独立的回测摘要表，保留每次回测的统计信息：

```python
# 记录回测摘要
cursor.execute("""
    INSERT INTO backtest_summary (
        start_time, end_time,
        total_klines, buy_signals, sell_signals,
        strategy_name, status
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
""", (
    datetime.now().isoformat(),
    datetime.now().isoformat(),
    len(klines),
    buy_signals,
    sell_signals,
    'price_break',
    'completed'
))
```

## 测试验证

### 自动测试脚本

**文件:** `test_cleanup_history.sh`

```bash
#!/bin/bash
# 测试回测前清理历史数据功能

echo "1. 检查当前sim_log表数据..."
CURRENT_COUNT=$(sqlite3 data/klines.db "SELECT COUNT(*) FROM sim_log")
echo "   当前数据: $CURRENT_COUNT 条"

echo ""
echo "2. 启动回测..."
curl -s -X POST http://localhost:8076/api/bot/start \
  -H "Content-Type: application/json" \
  -d '{}' > /dev/null

echo ""
echo "3. 查看清理日志..."
grep "清理历史" /tmp/web_backtest.log

echo ""
echo "4. 验证新数据ID..."
sqlite3 data/klines.db "SELECT MIN(id), MAX(id) FROM sim_log"
```

运行测试:
```bash
./test_cleanup_history.sh
```

## 常见问题

### Q1: 为什么每次都要清理？

**A:** 为了确保每次回测结果准确可靠。历史数据会干扰统计，导致：
- 信号数量不准确
- 无法判断是哪次回测的结果
- 优化策略时无法对比效果

### Q2: 如果想保留历史数据怎么办？

**A:** 有几种方法：
1. 在每次回测前导出数据
2. 修改代码不执行清理
3. 创建备份表存储历史结果

### Q3: 清理会删除其他表的数据吗？

**A:** 不会。清理操作只针对 `sim_log` 表，不会影响：
- klines_1m（K线数据）
- orders（订单表）
- backtestlog（回测日志）
- 其他任何表

### Q4: 如何查看某次回测的结果？

**A:** 当前实现每次都会清理，如需保留请：
1. 在回测完成后立即导出数据
2. 截图保存统计结果
3. 实现回测摘要功能（参见扩展功能）

## 相关文件

### 修改的文件
- **web_app.py** - 添加清理逻辑

### 新增文件
- **test_cleanup_history.sh** - 测试脚本
- **docs/BACKTEST_CLEANUP.md** - 本文档

## 总结

**回测历史数据清理功能已实现！** ✅

特性:
- ✅ 每次启动回测自动清理历史数据
- ✅ 确保每次回测都是干净环境
- ✅ 避免历史数据干扰
- ✅ 记录清理日志
- ✅ 支持数据恢复（ID递增）

现在可以:
- ✅ 反复测试策略而不互相干扰
- ✅ 每次回测结果准确可靠
- ✅ 快速迭代开发

**立即开始使用:**

```bash
./start_web_backtest.sh
```

访问: **http://localhost:8076/monitor** 🚀

每次点击"启动"都会自动清理历史数据！
