# 数据源适配器 - 统一数据接口

## 概述

数据源适配器（DataSourceAdapter）提供了统一的数据访问接口，可以在两种模式之间无缝切换：

1. **实盘模式** - 从Binance API获取实时数据
2. **回测/验证模式** - 从SQLite数据库读取历史数据

## 核心组件

### 1. DataSourceAdapter

**文件**: [data_module/data_source_adapter.py](data_module/data_source_adapter.py)

统一的数据访问接口，自动根据配置选择数据源。

```python
from data_module.data_source_adapter import create_data_source

# 自动检测模式（推荐）
adapter = create_data_source()

# 指定模式
adapter = create_data_source(mode='live')   # 实盘模式
adapter = create_data_source(mode='replay') # 回测模式
```

#### 主要方法

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `get_klines(limit=1000)` | 获取K线数据 | List[Dict] |
| `get_klines_by_time_range(start, end)` | 按时间范围获取K线 | List[Dict] |
| `get_latest_kline()` | 获取最新一条K线 | Dict or None |
| `get_warmup_data(days=200)` | 获取预热数据 | List[Dict] |
| `is_live_mode()` | 是否为实盘模式 | bool |
| `is_replay_mode()` | 是否为回测模式 | bool |
| `get_mode_info()` | 获取模式信息 | Dict |
| `print_mode_info()` | 打印模式信息 | None |

### 2. DbKlineReader

**文件**: [data_module/db_kline_reader.py](data_module/db_kline_reader.py)

从SQLite数据库读取K线数据。

```python
from data_module.db_kline_reader import DbKlineReader

reader = DbKlineReader(
    db_path='data/klines.db',
    table_name='klines_1m'
)

# 获取K线
klines = reader.get_klines(limit=1000)

# 按时间范围获取
klines = reader.get_klines_by_time_range(
    start_time='2023-01-01 00:00:00',
    end_time='2023-01-01 23:59:59'
)

# 获取预热数据
warmup = reader.get_warmup_data(days=200)

# 获取统计信息
total = reader.get_total_count()
time_range = reader.get_time_range()
```

## 模式配置

### 环境变量控制

#### 方式1: 环境变量

```bash
# 实盘模式（默认）
export DB_SIM_MODE=0
export REPLAY_MODE=0

# 回测/验证模式
export DB_SIM_MODE=1
# 或
export REPLAY_MODE=1
```

#### 方式2: 配置文件

**config.json**:
```json
{
    "DB_SIM_MODE": 0,
    "REPLAY_MODE": 0
}
```

#### 方式3: 代码中指定

```python
from data_module.data_source_adapter import DataSourceAdapter

# 实盘模式
adapter = DataSourceAdapter(mode='live')

# 回测模式
adapter = DataSourceAdapter(mode='replay')
```

## 使用示例

### 示例1: 实盘模式 - 获取实时数据

```python
from data_module.data_source_adapter import create_data_source

# 创建数据源（自动检测为实盘模式）
adapter = create_data_source()

# 获取最新1000条K线
klines = adapter.get_klines(limit=1000)

# 打印最新价格
if klines:
    latest = klines[-1]
    print(f"最新价格: {latest['close']}")
```

### 示例2: 回测模式 - 验证计算准确性

```python
import os
os.environ['DB_SIM_MODE'] = '1'  # 设置为回测模式

from data_module.data_source_adapter import create_data_source

# 创建数据源（自动检测为回测模式）
adapter = create_data_source()

# 打印模式信息
adapter.print_mode_info()

# 按时间范围获取数据
klines = adapter.get_klines_by_time_range(
    start_time='2023-01-01 00:00:00',
    end_time='2023-01-31 23:59:59'
)

print(f"获取到 {len(klines)} 条K线数据")

# 获取200天预热数据
warmup = adapter.get_warmup_data(days=200)
print(f"预热数据: {len(warmup)} 条")
```

### 示例3: 统一代码 - 自动适配

```python
from data_module.data_source_adapter import get_data_source

# 获取全局数据源实例（自动检测模式）
adapter = get_data_source()

# 统一的数据获取接口
klines = adapter.get_klines(limit=1000)

# 根据模式执行不同逻辑
if adapter.is_live_mode():
    print("实盘模式 - 发送真实订单")
    # send_real_order()
else:
    print("回测模式 - 模拟订单执行")
    # simulate_order()
```

## 测试验证

### 运行测试

```bash
# 使用bigtree环境
/Users/zhaosuqi/miniforge3/envs/bigtree/bin/python test_data_source_adapter.py
```

### 测试结果

```
============================================================
测试回测模式（SQLite数据库）
============================================================
初始化数据源适配器，模式: replay
数据库路径: /Users/zhaosuqi/work/monipan/data/klines.db
数据表名: klines_1m
============================================================
运行模式: 回测/验证模式
数据来源: SQLite数据库 (/Users/zhaosuqi/work/monipan/data/klines.db)
数据库路径: /Users/zhaosuqi/work/monipan/data/klines.db
数据表名: klines_1m
总记录数: 1567146
时间范围: 2023-01-01T00:00:00 至 2025-12-24T07:05:00
============================================================

获取最新10条K线...
成功获取 10 条K线
  [1] 2023-01-01T00:00:00 | O:16531.20 H:16531.20 L:16531.10 C:16531.10
  [2] 2023-01-01T00:01:00 | O:16531.10 H:16531.20 L:16531.10 C:16531.10
  ...

按时间范围获取K线...
获取到 1440 条K线数据（2023-01-01）

✅ 回测模式测试完成
```

## 数据格式

### K线数据结构

```python
{
    'id': 1,
    'open_time': '2023-01-01T00:00:00',
    'open': 16531.20,
    'high': 16531.20,
    'low': 16531.10,
    'close': 16531.10,
    'volume': 123.45,
    'close_time': '2023-01-01T00:00:59.999000',
    'quote_volume': 1234567.89,
    'trades': 1234,
    'taker_buy_base': 123.45,
    'taker_buy_quote': 1234567.89,
    'symbol': 'BTCUSD_PERP',
    'created_at': '2026-01-05 22:12:00'
}
```

## 模式对比

| 特性 | 实盘模式 | 回测/验证模式 |
|------|----------|---------------|
| **数据来源** | Binance API | SQLite数据库 |
| **数据类型** | 实时数据 | 历史数据 |
| **网络要求** | 需要网络连接 | 无需网络 |
| **API密钥** | 需要 | 不需要 |
| **订单执行** | 真实订单 | 模拟订单 |
| **主要用途** | 实盘交易 | 策略验证、回测 |
| **数据延迟** | 极低 | 无 |
| **配置变量** | `DB_SIM_MODE=0` | `DB_SIM_MODE=1` |

## 便捷函数

```python
from data_module.data_source_adapter import (
    is_live_mode,
    is_replay_mode,
    get_current_mode
)

# 快速检测模式
if is_live_mode():
    print("当前为实盘模式")
elif is_replay_mode():
    print("当前为回测模式")

# 获取模式字符串
mode = get_current_mode()  # 'live' or 'replay'
```

## 实际应用场景

### 场景1: 策略开发与验证

```python
# 开发阶段：使用历史数据验证
os.environ['DB_SIM_MODE'] = '1'
adapter = create_data_source()

# 回测策略
klines = adapter.get_klines_by_time_range(
    start_time='2023-01-01 00:00:00',
    end_time='2023-12-31 23:59:59'
)

# 验证指标计算准确性
for kline in klines:
    indicators = calculate_indicators(kline)
    # 验证逻辑...
```

### 场景2: 生产环境实盘交易

```python
# 生产环境：使用实时数据
os.environ['DB_SIM_MODE'] = '0'
adapter = create_data_source()

while True:
    # 获取最新数据
    klines = adapter.get_klines(limit=1000)

    # 计算指标
    indicators = calculate_indicators(klines)

    # 发送订单
    if should_buy(indicators):
        send_buy_order()

    time.sleep(60)
```

### 场景3: 统一代码库

```python
# 同一套代码，根据环境变量自动选择模式
from data_module.data_source_adapter import get_data_source

class TradingBot:
    def __init__(self):
        self.adapter = get_data_source()
        self.mode = self.adapter.get_mode_info()['mode']

    def run(self):
        while True:
            klines = self.adapter.get_klines(limit=1000)
            signal = self.calculate_signal(klines)

            if self.mode == 'live':
                self.execute_real_order(signal)
            else:
                self.simulate_order(signal)
```

## 数据库表结构

### klines_1m 表

```sql
CREATE TABLE klines_1m (
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
);

CREATE INDEX idx_klines_1m_open_time
ON klines_1m(open_time);
```

## 注意事项

1. **时间格式**: 数据库中时间使用ISO格式 `2023-01-01T00:00:00`，代码会自动处理空格和T两种格式
2. **数据去重**: 使用`open_time`作为唯一键，自动去重和更新
3. **模式切换**: 修改模式后需要重启程序才能生效
4. **预热数据**: 回测模式下，至少需要200天的预热数据用于1天MACD计算
5. **数据库连接**: 使用完毕后会自动关闭连接

## 相关文件

- [data_module/data_source_adapter.py](data_module/data_source_adapter.py) - 数据源适配器
- [data_module/db_kline_reader.py](data_module/db_kline_reader.py) - 数据库K线读取器
- [data_module/kline_fetcher.py](data_module/kline_fetcher.py) - Binance API获取器
- [test_data_source_adapter.py](test_data_source_adapter.py) - 测试脚本
- [core/config.py](core/config.py) - 配置管理

## 更新日期

2026-01-05
