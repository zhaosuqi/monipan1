# 回测逻辑详解

## 📊 完整流程

当你在Web界面设置回测时间段(例如: 2024-01-01 到 2024-01-10),系统会按照以下流程执行:

### 步骤1: 预热数据加载 (Warm-up Phase)

**目的**: 为了让技术指标(MACD、KDJ等)能够正确计算,需要加载开始时间之前的历史数据。

**示例**:
- 用户设置回测时间: `2024-01-01 00:00` 到 `2024-01-10 23:59`
- 预热天数配置: `REPLAY_WARM_DAYS=50`
- 实际加载数据:
  - **预热数据**: `2023-11-12 00:00` 到 `2023-12-31 23:59` (50天)
  - **回测数据**: `2024-01-01 00:00` 到 `2024-01-10 23:59` (10天)

**代码实现**:
```python
# 计算预热数据时间范围
preload_start = start_ts - pd.Timedelta(days=cfg.REPLAY_WARM_DAYS)  # 前50天
preload_end = start_ts - pd.Timedelta(minutes=1)  # 回测开始前1分钟

# 从数据库加载预热数据
query = f"""
    SELECT open_time, open, high, low, close, volume
    FROM `{cfg.HIST_TABLE}`
    WHERE open_time >= ? AND open_time <= ?
    ORDER BY open_time ASC
"""
df_warm = pd.read_sql_query(query, conn_warm, params=[preload_start, preload_end])

# 预热指标引擎
indicator_engine.seed_rows(records)
```

### 步骤2: 回测数据加载与模拟

**目的**: 按照每分钟K线顺序模拟交易。

**流程**:
1. 从数据库查询指定时间范围的K线数据
2. 按时间顺序逐条处理每根K线
3. 每根K线执行以下操作:
   - 更新技术指标
   - 触发交易信号
   - 执行开仓/平仓逻辑
   - 记录交易日志
   - 更新持仓状态

**代码实现**:
```python
# 主回测循环
for bar in iter_sqlite_bars(cfg.HIST_DB_PATH, cfg.HIST_TABLE,
                            start=start_ts, end=end_ts,
                            chunk_size=cfg.REPLAY_CHUNK):
    # 1. 更新指标
    indicators = indicator_engine.update(bar)

    # 2. 持久化指标数据
    persist_indicator_row(conn, cfg.MACD_OUTPUT_TABLE, bar, indicators)

    # 3. 执行交易逻辑
    engine.on_bar(bar, indicators)

    # 4. 定期刷新日志
    if bar_count % 500 == 0:
        flush_logs(conn, log_table, engine.logs)
```

## 🎯 具体示例

### 示例1: 短期回测

**配置**:
- 开始时间: `2024-01-01 00:00`
- 结束时间: `2024-01-10 23:59`
- 预热天数: `50天`

**实际执行**:
```
1. 加载预热数据:
   时间范围: 2023-11-12 00:00 至 2023-12-31 23:59
   数据量: ~72,000条 (50天 × 1440分钟/天)
   用途: 初始化MACD、KDJ等指标

2. 执行回测:
   时间范围: 2024-01-01 00:00 至 2024-01-10 23:59
   数据量: ~14,400条 (10天 × 1440分钟/天)
   操作: 模拟交易、记录日志

总计处理: ~86,400条K线
```

### 示例2: 年度回测

**配置**:
- 开始时间: `2024-01-01 00:00`
- 结束时间: `2024-12-31 23:59`
- 预热天数: `50天`

**实际执行**:
```
1. 加载预热数据:
   时间范围: 2023-11-12 00:00 至 2023-12-31 23:59
   数据量: ~72,000条

2. 执行回测:
   时间范围: 2024-01-01 00:00 至 2024-12-31 23:59
   数据量: ~525,600条 (365天 × 1440分钟/天)

总计处理: ~597,600条K线
预计耗时: 2-3小时
```

## 📁 数据流向

```
数据库 (klines.db)
    |
    ├─> 预热数据加载 (50天)
    |      ↓
    |   指标引擎初始化
    |   (MACD, KDJ预热)
    |
    └─> 回测数据逐条加载
           ↓
        更新指标
           ↓
        交易信号判断
           ↓
        订单模拟执行
           ↓
        持仓状态更新
           ↓
        交易日志记录
           ↓
        数据库保存 (sim_log, klines_1m_sim)
```

## ⚙️ 关键配置参数

### 预热配置

```python
# .env 或环境变量
REPLAY_WARM_DAYS=50       # 预热天数(默认50天)
REPLAY_CHUNK=2000         # 每次从数据库读取的K线数量
```

### 回测时间配置

```python
# Web界面或环境变量
REPLAY_START=2024-01-01   # 回测开始时间
REPLAY_END=2024-01-10     # 回测结束时间
```

## 📊 输出数据

### 1. 交易日志表 (sim_log)

```sql
SELECT * FROM sim_log ORDER BY id DESC LIMIT 10;
```

字段说明:
- `log_time`: 日志时间
- `event`: 事件类型(开仓/平仓/止损/止盈)
- `side`: 方向(long/short)
- `price`: 价格
- `contracts`: 合约数量
- `pnl`: 盈亏
- `details`: 详细信息

### 2. 模拟K线表 (klines_1m_sim)

```sql
SELECT COUNT(*) FROM klines_1m_sim;
```

包含回测期间的所有K线数据。

### 3. 指标数据表 (klines_1m_macd_calc)

```sql
SELECT * FROM klines_1m_macd_calc ORDER BY open_time DESC LIMIT 10;
```

包含每根K线的MACD、KDJ等指标值。

## 🔍 验证回测结果

### 1. 检查处理的数据量

```bash
sqlite3 data/klines.db "SELECT COUNT(*) FROM klines_1m_sim"
```

应该约等于: `(结束日期 - 开始日期 + 预热天数) × 1440`

### 2. 查看交易次数

```bash
sqlite3 data/klines.db "SELECT COUNT(*) FROM sim_log"
```

### 3. 计算总盈亏

```bash
sqlite3 data/klines.db "SELECT SUM(pnl) FROM sim_log"
```

### 4. 查看最新交易

```bash
sqlite3 data/klines.db "SELECT * FROM sim_log ORDER BY id DESC LIMIT 20"
```

## 🚀 性能优化

### 1. 分批加载

系统使用 `REPLAY_CHUNK=2000` 每次加载2000条K线,避免内存溢出。

### 2. 增量写入

每处理500条K线才写入一次数据库,减少IO操作。

```python
if bar_count % 500 == 0:
    flush_logs(conn, log_table, engine.logs)
```

### 3. 向量化计算

预热数据使用pandas向量化加载,提高速度。

```python
df_warm = pd.read_sql_query(query, conn_warm, params=params)
```

## 📝 回测日志示例

```
Replay mode ON. Source: data/klines.db table klines_1m, start=2024-01-01 00:00:00+00:00, end=2024-01-10 00:00:00+00:00
Replay filter params -> start=2024-01-01 00:00:00, end=2024-01-10 00:00:00
Replay stats check passed: database contains 1574954 bars
Preloaded 72000 bars before start boundary (from 2023-11-12 00:00:00+00:00 to 2023-12-31 23:59:00+00:00).
Processed 500 bars; last ts=2024-01-01 08:20:00+00:00, open positions=1, realized_pnl=-0.001000
Processed 1000 bars; last ts=2024-01-01 16:59:00+00:00, open positions=0, realized_pnl=0.002000
...
Replay finished. Bars processed=14400, realized_pnl=0.015000, open positions=0
```

## 🎯 最佳实践

1. **预热天数**: 建议50天,确保指标充分预热
2. **回测时间**: 建议至少1个月,才有统计意义
3. **数据验证**: 回测前先检查数据库是否有完整数据
4. **结果分析**: 重点关注盈亏比、最大回撤、胜率等指标

---

**总结**: 预热数据确保指标准确性,回测数据验证策略效果,两者结合才能得到可靠的回测结果!
