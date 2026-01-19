# 数据源快速使用指南

## 两种模式

### 模式1: 实盘模式（连接Binance）

从币安API获取实时数据，用于实盘交易。

```bash
# 设置环境变量
export DB_SIM_MODE=0
export REPLAY_MODE=0

# 运行程序
python your_trading_bot.py
```

**特点**:
- ✅ 实时数据
- ✅ 真实订单执行
- ⚠️ 需要API密钥
- ⚠️ 需要网络连接

### 模式2: 回测/验证模式（连接SQLite）

从本地数据库读取历史数据，用于验证计算准确性。

```bash
# 设置环境变量
export DB_SIM_MODE=1

# 运行程序
python your_trading_bot.py
```

**特点**:
- ✅ 无需网络
- ✅ 无需API密钥
- ✅ 快速验证
- ✅ 历史数据回放

## 统一接口

```python
from data_module.data_source_adapter import get_data_source

# 获取数据源（自动检测模式）
adapter = get_data_source()

# 获取K线数据
klines = adapter.get_klines(limit=1000)

# 按时间范围获取
klines = adapter.get_klines_by_time_range(
    start_time='2023-01-01 00:00:00',
    end_time='2023-01-31 23:59:59'
)

# 获取预热数据（200天）
warmup = adapter.get_warmup_data(days=200)
```

## 快速测试

```bash
# 测试回测模式
/Users/zhaosuqi/miniforge3/envs/bigtree/bin/python test_data_source_adapter.py
```

## 检查当前模式

```python
from data_module.data_source_adapter import is_live_mode, is_replay_mode

if is_live_mode():
    print("实盘模式")
elif is_replay_mode():
    print("回测模式")
```

## 数据准备

### 采集数据到数据库

```bash
# 获取最近7天数据
python fetch_klines.py --days 7 --db data/klines.db

# 获取指定时间范围
python fetch_klines.py --start "2023-01-01" --end "2023-12-31" --db data/klines.db

# 查询数据库
python fetch_klines.py --query --db data/klines.db --limit 10
```

## 数据库信息

当前数据库状态:
- 路径: `data/klines.db`
- 表名: `klines_1m`
- 记录数: 1,567,146 条
- 时间范围: 2023-01-01 至 2025-12-24

## 使用场景

### 场景1: 验证指标计算

```python
import os
os.environ['DB_SIM_MODE'] = '1'

from data_module.data_source_adapter import create_data_source

adapter = create_data_source()

# 获取历史数据
klines = adapter.get_klines_by_time_range(
    start_time='2023-01-01 00:00:00',
    end_time='2023-12-31 23:59:59'
)

# 计算指标并验证
for kline in klines:
    macd = calculate_macd(kline)
    # 验证计算结果...
```

### 场景2: 实盘交易

```python
import os
os.environ['DB_SIM_MODE'] = '0'

from data_module.data_source_adapter import create_data_source

adapter = create_data_source()

while True:
    # 获取实时数据
    klines = adapter.get_klines(limit=1000)

    # 计算信号
    signal = calculate_signal(klines)

    # 执行交易
    if signal == 'BUY':
        execute_buy_order()

    time.sleep(60)
```

### 场景3: 统一代码

```python
from data_module.data_source_adapter import get_data_source

class TradingBot:
    def __init__(self):
        self.adapter = get_data_source()

    def run(self):
        klines = self.adapter.get_klines(limit=1000)
        signal = self.calculate_signal(klines)

        # 自动适配模式
        if self.adapter.is_live_mode():
            self.execute_real_order(signal)
        else:
            self.simulate_order(signal)
```

## 配置示例

### .env 文件

```bash
# 实盘模式
DB_SIM_MODE=0
REPLAY_MODE=0
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret

# 回测模式
# DB_SIM_MODE=1
# HIST_DB_PATH=data/klines.db
# HIST_TABLE=klines_1m
```

## 常见问题

**Q: 如何切换模式？**
A: 修改环境变量 `DB_SIM_MODE` (0=实盘, 1=回测)

**Q: 回测模式需要网络吗？**
A: 不需要，数据来自本地SQLite数据库

**Q: 如何准备历史数据？**
A: 使用 `fetch_klines.py` 脚本采集数据到数据库

**Q: 数据格式是什么？**
A: 统一的字典格式，包含 OHLCV 数据

## 相关文档

- [DATA_SOURCE_ADAPTER.md](DATA_SOURCE_ADAPTER.md) - 完整文档
- [DATA_MODULE_MODES.md](DATA_MODULE_MODES.md) - 模式说明
- [SQLITE_QUICK_GUIDE.md](SQLITE_QUICK_GUIDE.md) - 数据库使用指南
