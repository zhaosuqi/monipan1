#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据模块模式说明

数据模块支持两种运行模式:
1. 实盘模式 (LIVE MODE) - 从Binance API获取实时数据
2. 回测模式 (REPLAY MODE) - 从数据库读取历史数据进行回测

## 模式切换

### 方式1: 环境变量控制
```bash
# 实盘模式
export DB_SIM_MODE=0
python main.py

# 回测模式
export DB_SIM_MODE=1
python main.py
```

### 方式2: 配置文件控制
```json
{
    "DB_SIM_MODE": 0
}
```

### 方式3: 命令行参数
```bash
python main.py --mode replay
python main.py --mode live
```

## 模式特性对比

### 实盘模式 (DB_SIM_MODE=0)

**数据来源**: Binance API实时数据

**适用场景**:
- 实盘交易
- 实时监控
- 生产环境

**功能**:
- ✅ 实时K线获取
- ✅ 实时指标计算
- ✅ 实时信号生成
- ✅ 实时订单执行
- ✅ 数据保存到数据库

**数据流**:
```
Binance API → KlineFetcher → IndicatorCalculator → SignalCalculator → OrderExecutor → 数据库
```

### 回测模式 (DB_SIM_MODE=1)

**数据来源**: 数据库历史数据

**适用场景**:
- 策略回测
- 参数优化
- 历史分析
- 测试验证

**功能**:
- ✅ 从数据库读取历史K线
- ✅ 历史数据回放
- ✅ 指标计算与更新
- ✅ 模拟信号生成
- ✅ 模拟订单执行
- ✅ 回测结果统计

**数据流**:
```
数据库 → ReplayEngine → IndicatorCalculator → SignalCalculator → OrderExecutor → 回测日志
```

## 实现架构

### 1. 配置管理 (core/config.py)

```python
class Config:
    def _load_env(self):
        # 模式配置
        self.DB_SIM_MODE = os.getenv('DB_SIM_MODE', '0').lower() in ('1', 'true', 'yes')
        self.REPLAY_MODE = os.getenv('REPLAY_MODE', '0').lower() in ('1', 'true', 'yes')

        # 数据库配置
        self.DB_PATH = os.getenv('DB_PATH', str(self.data_dir / 'klines.db'))
        self.HIST_DB_PATH = os.getenv('HIST_DB_PATH', str(self.data_dir / 'klines.db'))
```

### 2. 数据源适配器 (data_module/data_source.py)

```python
class DataSourceAdapter:
    """数据源适配器 - 统一两种模式的数据接口"""

    def __init__(self, mode: str = 'live'):
        self.mode = mode  # 'live' or 'replay'

        if mode == 'live':
            from .kline_fetcher import KlineFetcher
            self.source = KlineFetcher()
        else:
            from .replay_engine import ReplayEngine
            self.source = ReplayEngine()

    def get_klines(self, limit: int = 1000):
        """统一的数据获取接口"""
        if self.mode == 'live':
            return self.source.fetch_latest_klines(limit)
        else:
            # 回测模式需要特殊处理
            return self.source.get_historical_klines()
```

### 3. 主程序适配 (main.py)

```python
from core.config import config

def main():
    mode = 'replay' if config.DB_SIM_MODE else 'live'

    logger.info(f"运行模式: {mode}")

    if mode == 'live':
        # 实盘模式
        run_live_mode()
    else:
        # 回测模式
        run_replay_mode()

def run_live_mode():
    """实盘模式"""
    from data_module import KlineFetcher, IndicatorCalculator
    from signal_module import SignalCalculator
    from trade_module import OrderExecutor

    fetcher = KlineFetcher()
    # ... 实盘逻辑

def run_replay_mode():
    """回测模式"""
    from data_module import ReplayEngine
    # ... 回测逻辑
```

## 使用示例

### 实盘模式
```bash
# 设置环境变量
export DB_SIM_MODE=0

# 运行
python main.py

# 或命令行
python main.py --mode live
```

### 回测模式
```bash
# 设置环境变量
export DB_SIM_MODE=1

# 运行
python main.py

# 或命令行
python main.py --mode replay
```

## 数据源配置

### 实盘模式配置
```python
# .env 或环境变量
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
BINANCE_TESTNET=0
SYMBOL=BTCUSD_PERP
KLINE_INTERVAL=1m
KLINE_LIMIT=1000
```

### 回测模式配置
```python
# .env 或环境变量
DB_SIM_MODE=1
HIST_DB_PATH=data/klines.db
HIST_TABLE=klines_1m
REPLAY_START=2024-01-01 00:00:00
REPLAY_END=2024-01-10 23:59:59
REPLAY_WARM_DAYS=200
REPLAY_CHUNK=2000
```

## 模式检测

```python
def get_current_mode():
    """获取当前运行模式"""
    from core.config import config

    if config.DB_SIM_MODE or config.REPLAY_MODE:
        return 'replay'
    else:
        return 'live'

def is_replay_mode():
    """是否为回测模式"""
    from core.config import config
    return config.DB_SIM_MODE or config.REPLAY_MODE

def is_live_mode():
    """是否为实盘模式"""
    return not is_replay_mode()
```

## 数据流向对比

### 实盘模式数据流
```
1. Binance API (实时数据)
   ↓
2. KlineFetcher.fetch_latest_klines()
   ↓
3. 保存到数据库 (可选)
   ↓
4. IndicatorCalculator.calculate_all()
   ↓
5. SignalCalculator.calculate_signal()
   ↓
6. OrderExecutor.execute_order()
   ↓
7. 订单发送到Binance
   ↓
8. 持仓更新
```

### 回测模式数据流
```
1. 数据库 (历史数据)
   ↓
2. ReplayEngine.load_warm_data() (预热)
   ↓
3. ReplayEngine.replay_loop()
   ↓
4. 逐条读取历史K线
   ↓
5. IndicatorCalculator.update()
   ↓
6. SignalCalculator.calculate_signal()
   ↓
7. OrderExecutor.simulate_order()
   ↓
8. 回测日志 (sim_log)
   ↓
9. 统计结果
```

## 接口统一

### 统一的K线获取接口
```python
class UnifiedDataFetcher:
    """统一的数据获取接口"""

    def __init__(self):
        self.mode = 'replay' if config.DB_SIM_MODE else 'live'

        if self.mode == 'live':
            self.fetcher = KlineFetcher()
        else:
            self.fetcher = ReplayEngine()

    def fetch_klines(self, **kwargs):
        """统一的获取接口"""
        if self.mode == 'live':
            return self.fetcher.fetch_latest_klines(**kwargs)
        else:
            return self.fetcher.get_replay_klines(**kwargs)
```

## 配置建议

### 开发环境
```bash
# 使用回测模式快速验证
export DB_SIM_MODE=1
export REPLAY_START=2024-01-01
export REPLAY_END=2024-01-07
```

### 生产环境
```bash
# 使用实盘模式
export DB_SIM_MODE=0
export BINANCE_API_KEY=xxx
export BINANCE_API_SECRET=xxx
```

## 验证模式

```python
from core.config import config

print(f"当前模式: {'回测' if config.DB_SIM_MODE else '实盘'}")
print(f"DB_SIM_MODE: {config.DB_SIM_MODE}")
print(f"REPLAY_MODE: {config.REPLAY_MODE}")
```

## 注意事项

1. **模式互斥**: 实盘和回测模式不能同时运行
2. **配置切换**: 修改模式后需要重启程序
3. **数据隔离**: 实盘数据和回测数据建议分开存储
4. **风险控制**: 回测模式不会发送真实订单

## 相关文件

- [core/config.py](core/config.py) - 配置管理
- [data_module/kline_fetcher.py](data_module/kline_fetcher.py) - 实盘数据获取
- [data_module/replay_engine.py](data_module/replay_engine.py) - 回测引擎
- [main.py](main.py) - 主程序入口

## 更新日期

2026-01-05
