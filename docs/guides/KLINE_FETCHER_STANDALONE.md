# K线数据获取模块独立运行指南

## 概述

K线数据获取模块现在可以独立运行,不依赖其他模块(如config、logger等)。

## 独立脚本

### [fetch_klines.py](fetch_klines.py)

完全独立的K线数据获取工具,可以单独使用。

### 特性

- ✅ **零依赖**: 不依赖项目的config、logger等模块
- ✅ **独立配置**: 支持命令行参数、环境变量、配置文件
- ✅ **多格式输出**: 支持JSON、CSV格式
- ✅ **灵活查询**: 支持最新N条、指定天数、指定时间范围

## 使用方法

### 1. 安装依赖

```bash
pip install python-binance
```

### 2. 基本使用

#### 获取最新1000条K线
```bash
python fetch_klines.py
```

#### 获取最新500条K线
```bash
python fetch_klines.py --limit 500
```

#### 获取最近7天的K线
```bash
python fetch_klines.py --days 7
```

#### 指定时间范围
```bash
python fetch_klines.py --start "2024-01-01" --end "2024-01-10"
```

#### 指定交易对和时间周期
```bash
python fetch_klines.py --symbol ETHUSD_PERP --interval 15m --days 3
```

### 3. 保存数据

#### 保存为JSON格式
```bash
python fetch_klines.py --days 7 --output klines.json
```

#### 保存为CSV格式
```bash
python fetch_klines.py --days 7 --output klines.csv
```

### 4. 使用配置文件

创建配置文件 `config.json`:
```json
{
    "SYMBOL": "BTCUSD_PERP",
    "KLINE_INTERVAL": "1m",
    "KLINE_LIMIT": 1000,
    "BINANCE_TESTNET": false
}
```

使用配置文件:
```bash
python fetch_klines.py --config config.json
```

### 5. 使用测试网
```bash
python fetch_klines.py --testnet
```

## 命令行参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--limit` | 获取最新N条 | `--limit 500` |
| `--days` | 获取最近N天 | `--days 7` |
| `--start` | 开始时间 | `--start "2024-01-01"` |
| `--end` | 结束时间 | `--end "2024-01-10"` |
| `--symbol` | 交易对 | `--symbol ETHUSD_PERP` |
| `--interval` | K线间隔 | `--interval 15m` |
| `--output` | 输出文件 | `--output data.json` |
| `--config` | 配置文件 | `--config config.json` |
| `--testnet` | 使用测试网 | `--testnet` |

## 环境变量

可以通过环境变量配置:

```bash
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"
export SYMBOL="BTCUSD_PERP"
export KLINE_INTERVAL="1m"
export KLINE_LIMIT="1000"

python fetch_klines.py
```

## 输出示例

### 控制台输出
```
[INFO] 2026-01-05 22:15:30 - 使用Binance主网
[INFO] 2026-01-05 22:15:31 - 获取最近7天的历史K线...
[INFO] 2026-01-05 22:15:32 - 获取K线: 2024-12-29 22:15:30 至 2025-01-05 22:15:30
[INFO] 2026-01-05 22:15:33 - 成功获取1000条K线
[INFO] 2026-01-05 22:15:33 - 已获取1000条K线
[INFO] 2026-01-05 22:15:34 - 获取K线: 2024-12-30 18:23:00 至 2025-01-05 22:15:30
[INFO] 2026-01-05 22:15:34 - 成功获取1000条K线
...
[INFO] 2026-01-05 22:15:45 - 获取历史K线完成: 10080条

============================================================
K线数据统计
============================================================
交易对: BTCUSD_PERP
K线间隔: 1m
数据条数: 10080
时间范围: 2024-12-29 22:16:00 至 2025-01-05 22:15:00
最新价格: 102345.67
============================================================

前5条数据:
  2024-12-29 22:16:00 | O:102234.56 H:102345.67 L:102123.45 C:102345.67 V:1234.56
  2024-12-29 22:17:00 | O:102345.67 H:102456.78 L:102234.56 C:102345.67 V:2345.67
  ...
```

## 数据格式

### JSON格式
```json
[
  {
    "open_time": 1704224400000,
    "open": 102234.56,
    "high": 102345.67,
    "low": 102123.45,
    "close": 102345.67,
    "volume": 1234.56,
    "close_time": 1704224459999,
    "quote_volume": 123456789.12,
    "trades": 12345,
    "taker_buy_base": 1234.56,
    "taker_buy_quote": 123456789.12
  }
]
```

### CSV格式
```csv
open_time,open,high,low,close,volume,close_time,quote_volume,trades,taker_buy_base,taker_buy_quote
1704224400000,102234.56,102345.67,102123.45,102345.67,1234.56,1704224459999,123456789.12,12345,1234.56,123456789.12
```

## 集成到项目

### 方式1: 直接使用独立脚本

```bash
# 在其他脚本中调用
python fetch_klines.py --days 7 --output data/klines.json
```

### 方式2: 作为模块导入

```python
# 在其他Python代码中使用
from fetch_klines import StandaloneKlineFetcher, SimpleConfig

config = SimpleConfig()
config.SYMBOL = "BTCUSD_PERP"
config.KLINE_INTERVAL = "1m"

fetcher = StandaloneKlineFetcher(config)
klines = fetcher.fetch_latest_klines(limit=1000)
```

### 方式3: 使用项目模块(需要依赖)

```python
# 如果项目模块可用
from data_module.kline_fetcher import KlineFetcher
from core.config import config

fetcher = KlineFetcher()
klines = fetcher.fetch_latest_klines()
```

## 对比

| 特性 | 独立脚本 (fetch_klines.py) | 项目模块 (kline_fetcher.py) |
|------|---------------------------|----------------------------|
| 依赖 | 仅python-binance | config, logger, database |
| 配置 | 命令行/环境变量/文件 | config模块 |
| 日志 | 简单控制台输出 | 完整日志系统 |
| 数据保存 | JSON/CSV | 数据库 |
| 适用场景 | 快速获取数据 | 集成到项目 |

## 最佳实践

### 1. 快速数据获取
使用独立脚本快速获取数据:
```bash
python fetch_klines.py --days 30 --output btc_klines_30d.json
```

### 2. 数据分析
获取数据后进行分析:
```python
import json
import pandas as pd

# 读取数据
with open('btc_klines_30d.json') as f:
    klines = json.load(f)

# 转换为DataFrame
df = pd.DataFrame(klines)
df['datetime'] = pd.to_datetime(df['open_time'], unit='ms')

# 分析
print(df.describe())
```

### 3. 定期备份
定期获取并备份数据:
```bash
#!/bin/bash
# backup_klines.sh
DATE=$(date +%Y%m%d)
python fetch_klines.py --days 7 --output "klines_${DATE}.json"
```

## 注意事项

1. **API限制**: Binance API有请求频率限制,大量获取数据时请注意
2. **网络连接**: 需要稳定的网络连接
3. **时间范围**: 单次请求最多获取1000条K线
4. **历史数据**: 需要循环获取长时间范围的数据

## 故障排除

### 问题1: 导入错误
```
ModuleNotFoundError: No module named 'binance'
```
**解决**:
```bash
pip install python-binance
```

### 问题2: API连接失败
```
ConnectionError: Failed to establish connection
```
**解决**:
- 检查网络连接
- 检查是否需要代理
- 尝试使用测试网: `--testnet`

### 问题3: 认证失败
```
Error: Invalid API-key
```
**解决**:
- 检查API Key是否正确
- 确认API Key有相应权限
- 主网和测试网的API Key不同

## 相关文件

- [fetch_klines.py](fetch_klines.py) - 独立K线获取脚本
- [data_module/kline_fetcher.py](data_module/kline_fetcher.py) - 项目集成版本
- [core/config.py](core/config.py) - 配置管理

## 更新日期

2026-01-05
