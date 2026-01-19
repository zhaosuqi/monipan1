# SQLite数据库集成 - 快速使用指南

## 快速开始

### 1. 保存K线到SQLite

```bash
# 激活环境
conda activate bigtree

# 保存最新100条到数据库
python fetch_klines.py --limit 100 --db klines.db

# 保存最近7天到数据库
python fetch_klines.py --days 7 --db klines.db

# 保存指定时间范围
python fetch_klines.py --start "2024-01-01" --end "2024-01-10" --db klines.db
```

### 2. 查询SQLite数据

```bash
# 查询最新10条
python fetch_klines.py --query --db klines.db --limit 10

# 查询指定表
python fetch_klines.py --query --db klines.db --table klines_1m_BTCUSD_PERP --limit 10
```

## 表名规则

### 自动表名
- **默认表名**: `klines_1m`
- **带交易对**: `klines_1m_BTCUSD_PERP`、`klines_1m_ETHUSD_PERP`

### 使用方式
```bash
# 方式1: 使用默认表名
python fetch_klines.py --limit 100 --db klines.db --table my_table

# 方式2: 自动使用交易对表名
python fetch_klines.py --symbol BTCUSD_PERP --limit 100 --db klines.db
# 自动创建表: klines_1m_BTCUSD_PERP
```

## 常用命令

### 数据采集
```bash
# 获取最新数据并保存
python fetch_klines.py --limit 1000 --db data/klines.db

# 获取历史数据
python fetch_klines.py --days 30 --db data/klines.db

# 多交易对采集
python fetch_klines.py --symbol BTCUSD_PERP --days 7 --db data/klines.db
python fetch_klines.py --symbol ETHUSD_PERP --days 7 --db data/klines.db
```

### 数据查询
```bash
# 查询最新数据
python fetch_klines.py --query --db data/klines.db --limit 20

# 查询指定表
python fetch_klines.py --query --db data/klines.db --table klines_1m_BTCUSD_PERP
```

### SQL查询
```bash
# 查看所有表
sqlite3 klines.db ".tables"

# 查看表结构
sqlite3 klines.db ".schema klines_1m_BTCUSD_PERP"

# 统计记录数
sqlite3 klines.db "SELECT COUNT(*) FROM klines_1m_BTCUSD_PERP"

# 查看时间范围
sqlite3 klines.db "SELECT MIN(open_time), MAX(open_time) FROM klines_1m_BTCUSD_PERP"

# 查询最新10条
sqlite3 klines.db "SELECT * FROM klines_1m_BTCUSD_PERP ORDER BY open_time DESC LIMIT 10"
```

## 数据库表结构

```sql
CREATE TABLE klines_1m_BTCUSD_PERP (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    open_time TEXT UNIQUE NOT NULL,      -- 开盘时间(唯一键)
    open REAL NOT NULL,                   -- 开盘价
    high REAL NOT NULL,                   -- 最高价
    low REAL NOT NULL,                    -- 最低价
    close REAL NOT NULL,                  -- 收盘价
    volume REAL NOT NULL,                 -- 成交量
    close_time TEXT NOT NULL,             -- 收盘时间
    quote_volume REAL NOT NULL,           -- 成交额
    trades INTEGER NOT NULL,              -- 成交笔数
    taker_buy_base REAL NOT NULL,         -- 主动买入量
    taker_buy_quote REAL NOT NULL,        -- 主动买入额
    symbol TEXT,                          -- 交易对
    created_at TEXT DEFAULT CURRENT_TIMESTAMP  -- 创建时间
)

CREATE INDEX idx_klines_1m_BTCUSD_PERP_open_time
ON klines_1m_BTCUSD_PERP(open_time)
```

## 特性说明

### ✅ 自动去重
- 使用`open_time`作为唯一键
- 已存在的数据自动更新
- 避免重复插入

### ✅ 增量更新
```bash
# 多次运行会自动更新已存在数据
python fetch_klines.py --limit 100 --db klines.db
python fetch_klines.py --limit 100 --db klines.db  # 第二次会更新已存在数据
```

### ✅ 多交易对支持
```bash
# 不同交易对保存到不同表
python fetch_klines.py --symbol BTCUSD_PERP --days 7 --db klines.db
# 表: klines_1m_BTCUSD_PERP

python fetch_klines.py --symbol ETHUSD_PERP --days 7 --db klines.db
# 表: klines_1m_ETHUSD_PERP
```

## 使用示例

### 示例1: 定时采集
```bash
#!/bin/bash
# collect_klines.sh

while true; do
    echo "采集数据: $(date)"
    python fetch_klines.py --limit 1000 --db data/klines.db
    echo "等待1小时..."
    sleep 3600
done
```

### 示例2: 批量采集多个交易对
```bash
#!/bin/bash
# collect_multiple.sh

SYMBOLS="BTCUSD_PERP ETHUSD_PERP BNBUSD_PERP SOLUSD_PERP"

for symbol in $SYMBOLS; do
    echo "采集 $symbol"
    python fetch_klines.py --symbol $symbol --days 7 --db data/klines.db
done
```

### 示例3: 历史数据补全
```bash
# 补全历史数据
python fetch_klines.py --start "2024-01-01" --end "2024-12-31" --db data/klines.db
```

## 命令行参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--db DB` | 数据库文件路径 | `--db klines.db` |
| `--table TABLE` | 表名 | `--table my_table` |
| `--symbol SYMBOL` | 交易对(自动建表) | `--symbol ETHUSD_PERP` |
| `--query` | 查询模式 | `--query` |
| `--limit N` | 限制数量 | `--limit 100` |

## 注意事项

1. **表名自动生成**: 指定`--symbol`时,表名会自动包含交易对
2. **数据去重**: 相同`open_time`的数据会自动更新
3. **索引自动创建**: 首次创建表时自动建立索引
4. **时间格式**: 数据库中时间使用ISO格式字符串

## 故障排除

### 问题1: 表不存在
```bash
# 确认表名(可能包含交易对后缀)
sqlite3 klines.db ".tables"
```

### 问题2: 数据重复
```bash
# 系统会自动去重,基于open_time唯一键
# 不需要手动处理重复数据
```

### 问题3: 查询无结果
```bash
# 检查表名是否正确
python fetch_klines.py --query --db klines.db --table 正确的表名
```

## 相关文档

- [SQLITE_INTEGRATION_COMPLETE.md](SQLITE_INTEGRATION_COMPLETE.md) - 完整功能说明
- [fetch_klines.py](fetch_klines.py) - 脚本文件

## 更新日期

2026-01-05
