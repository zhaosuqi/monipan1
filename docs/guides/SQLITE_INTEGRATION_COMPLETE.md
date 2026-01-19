# SQLite数据库集成完成总结

## 完成时间
2026-01-05 22:12

## 概述

K线数据获取脚本已成功集成SQLite数据库支持,可以直接保存K线数据到数据库。

## 新增功能

### 1. SQLite保存功能 ✅

#### 自动创建表结构
```sql
CREATE TABLE IF NOT EXISTS {table_name} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    open_time TEXT UNIQUE NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    close_time TEXT NOT NULL,
    quote_volume REAL NOT NULL,
    trades INTEGER NOT NULL,
    taker_buy_base REAL NOT NULL,
    taker_buy_quote REAL NOT NULL,
    symbol TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
```

#### 自动创建索引
```sql
CREATE INDEX IF NOT EXISTS idx_{table_name}_open_time
ON {table_name}(open_time)
```

#### 智能表名
- 默认表名: `klines_1m`
- 带交易对表名: `klines_1m_BTCUSD_PERP`、`klines_1m_ETHUSD_PERP`等

### 2. 数据插入/更新 ✅

#### 插入新数据
```python
# 自动检测并插入新数据
fetcher.save_to_sqlite(klines, "klines.db")
```

#### 更新已存在数据
```python
# 如果open_time已存在,自动更新
# 支持去重和增量更新
```

#### 统计信息
```
数据已保存到SQLite: klines.db
  表名: klines_1m_BTCUSD_PERP
  新增: 20条
  更新: 0条
  总计: 20条
```

### 3. 数据查询功能 ✅

#### 查询最新数据
```bash
python fetch_klines.py --query --db klines.db --limit 10
```

#### 查询结果
```
============================================================
数据库查询结果
============================================================
数据库: klines.db
表名: klines_1m_BTCUSD_PERP
数据条数: 5
时间范围: 2026-01-05 22:08:00 至 2026-01-05 22:12:00
最新价格: 92709.1
============================================================
```

## 使用方法

### 1. 保存到数据库

#### 保存到默认表
```bash
python fetch_klines.py --limit 100 --db klines.db
# 表名: klines_1m
```

#### 保存到指定表
```bash
python fetch_klines.py --limit 100 --db klines.db --table my_table
# 表名: my_table
```

#### 自动使用交易对表名
```bash
python fetch_klines.py --symbol BTCUSD_PERP --limit 100 --db klines.db
# 表名: klines_1m_BTCUSD_PERP

python fetch_klines.py --symbol ETHUSD_PERP --limit 100 --db klines.db
# 表名: klines_1m_ETHUSD_PERP
```

### 2. 查询数据库

#### 查询最新10条
```bash
python fetch_klines.py --query --db klines.db --limit 10
```

#### 查询指定表
```bash
python fetch_klines.py --query --db klines.db --table klines_1m_BTCUSD_PERP
```

#### 同时获取和保存
```bash
# 获取并保存到数据库
python fetch_klines.py --days 7 --db data/klines.db

# 然后查询验证
python fetch_klines.py --query --db data/klines.db --limit 10
```

## 数据库特性

### 1. 自动去重 ✅
- 使用`open_time`作为唯一键
- 已存在的数据自动更新
- 避免重复插入

### 2. 时间戳转换 ✅
```python
# Unix时间戳 -> ISO格式字符串
open_time: 1704224400000 -> "2024-01-05T22:00:00"
close_time: 1704224459999 -> "2024-01-05T22:00:59.999000"
```

### 3. 多交易对支持 ✅
```bash
# 保存多个交易对
python fetch_klines.py --symbol BTCUSD_PERP --days 7 --db klines.db
python fetch_klines.py --symbol ETHUSD_PERP --days 7 --db klines.db

# 数据库会创建两个表
# - klines_1m_BTCUSD_PERP
# - klines_1m_ETHUSD_PERP
```

### 4. 索引优化 ✅
- 自动在`open_time`上创建索引
- 提高查询性能
- 支持快速时间范围查询

## 测试验证

### 测试1: 保存功能 ✅
```bash
python fetch_klines.py --limit 20 --db test_klines.db

# 结果:
# ✓ 成功保存20条数据
# ✓ 表名: klines_1m_BTCUSD_PERP
# ✓ 新增: 20条
```

### 测试2: 查询功能 ✅
```bash
python fetch_klines.py --query --db test_klines.db --table klines_1m_BTCUSD_PERP --limit 5

# 结果:
# ✓ 成功查询5条数据
# ✓ 显示时间范围和价格
```

## 命令行参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--db` | 数据库文件路径 | `--db klines.db` |
| `--table` | 表名 | `--table klines_1m` |
| `--query` | 查询模式 | `--query` |
| `--symbol` | 交易对(自动创建表) | `--symbol ETHUSD_PERP` |

## 数据库表结构

### 字段说明
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键,自增 |
| open_time | TEXT | 开盘时间(唯一键) |
| open | REAL | 开盘价 |
| high | REAL | 最高价 |
| low | REAL | 最低价 |
| close | REAL | 收盘价 |
| volume | REAL | 成交量 |
| close_time | TEXT | 收盘时间 |
| quote_volume | REAL | 成交额 |
| trades | INTEGER | 成交笔数 |
| taker_buy_base | REAL | 主动买入量 |
| taker_buy_quote | REAL | 主动买入额 |
| symbol | TEXT | 交易对符号 |
| created_at | TEXT | 创建时间 |

## SQL查询示例

### 查看所有表
```bash
sqlite3 klines.db ".tables"
```

### 查看表结构
```bash
sqlite3 klines.db ".schema klines_1m_BTCUSD_PERP"
```

### 统计记录数
```bash
sqlite3 klines.db "SELECT COUNT(*) FROM klines_1m_BTCUSD_PERP"
```

### 查询时间范围
```bash
sqlite3 klines.db "SELECT MIN(open_time), MAX(open_time) FROM klines_1m_BTCUSD_PERP"
```

### 查询最新数据
```bash
sqlite3 klines.db "SELECT * FROM klines_1m_BTCUSD_PERP ORDER BY open_time DESC LIMIT 10"
```

## 使用场景

### 场景1: 定时采集
```bash
#!/bin/bash
# 每小时采集最新数据
while true; do
    python fetch_klines.py --limit 100 --db data/klines.db
    sleep 3600
done
```

### 场景2: 多交易对采集
```bash
# 采集多个交易对数据
for symbol in BTCUSD_PERP ETHUSD_PERP BNBUSD_PERP; do
    python fetch_klines.py --symbol $symbol --days 7 --db data/klines.db
done
```

### 场景3: 增量更新
```bash
# 获取最新数据并更新数据库
python fetch_klines.py --limit 1000 --db data/klines.db
# 自动去重和更新已存在的数据
```

### 场景4: 数据验证
```bash
# 查询并验证数据
python fetch_klines.py --query --db data/klines.db --limit 10
```

## 性能特性

| 特性 | 说明 |
|------|------|
| 批量插入 | 支持一次性插入大量数据 |
| 自动去重 | 基于open_time唯一键 |
| 增量更新 | 已存在数据自动更新 |
| 索引优化 | open_time索引提高查询速度 |
| 事务安全 | 使用数据库事务保证数据一致性 |

## 相关文件

- [fetch_klines.py](fetch_klines.py) - 独立K线获取脚本(含SQLite支持)
- [data/klines.db](data/klines.db) - 项目主数据库
- [KLINE_FETCHER_COMPLETE.md](KLINE_FETCHER_COMPLETE.md) - K线获取功能总结

## 下一步建议

1. **数据分析**: 使用pandas直接从SQLite读取数据
2. **可视化**: 从数据库读取并生成K线图表
3. **策略回测**: 结合回测引擎使用数据库数据
4. **定时任务**: 设置crontab定期采集数据
5. **数据备份**: 定期备份SQLite数据库

## 总结

✅ SQLite数据库集成完成
✅ 自动创建表和索引
✅ 支持插入和更新操作
✅ 支持查询功能
✅ 多交易对支持
✅ 测试验证通过

**现在可以将K线数据直接保存到SQLite数据库中!**
