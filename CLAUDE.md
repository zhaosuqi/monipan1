# BTCUSD_PERP 量化交易系统 - 业务逻辑文档

## 重要提示

**交易策略安全**: trade_module 和 signal_module 的修改需经确认后提交，以确保交易策略的稳定性和安全性。

## 系统架构

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Data Layer     │───▶│  Trading Layer  │───▶│    Web Layer    │
│  (数据层)        │    │   (交易层)       │    │   (展示层)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 数据流

### 1. K线数据流
```
币安交易所 ──▶ realtime_kline_sync.py ──▶ klines_1m 表
                                              │
                                              ▼
                                   sync_macd_indicators.py
                                              │
                                              ▼
                                   klines_1m_macd_smooth_ma 表
```

### 2. 交易信号流
```
klines_1m_macd_smooth_ma 表 ──▶ db_driven_trading.py
                                        │
                                        ▼
                              SignalCalculator (V5策略)
                                        │
                                        ▼
                              TradeEngine.process_tick()
                                        │
                              ├─▶ 开仓/止盈/止损/回撤判断
                              │
                              ▼
                        币安交易所下单
```

### 3. 交易记录流
```
TradeEngine ──▶ trade_recorder.py ──┬──▶ trade_records 表 (交易明细)
                                    └──▶ position_records 表 (持仓记录)
```

## 核心模块

| 模块 | 路径 | 功能 |
|-----|------|------|
| K线同步 | `data/realtime_kline_sync.py` | WebSocket获取币安K线 |
| 指标计算 | `data/sync_macd_indicators.py` | MACD/J指标计算 |
| 交易入口 | `data/db_driven_trading.py` | 监控指标表，执行交易 |
| 交易引擎 | `trade_module/trade_engine.py` | 开仓/平仓/止盈/止损逻辑 |
| 交易记录 | `core/trade_recorder.py` | 持久化交易数据 |
| Web服务 | `web/kline_viewer.py` | K线图/参数展示 |
| 数据同步 | `scripts/sync_trades_from_binance.py` | 币安历史数据同步 |

## 数据库表

### klines_1m - 原始K线
- open_time, open, high, low, close, volume

### klines_1m_macd_smooth_ma - 指标数据
- 15m/1h/4h/1d 周期的 MACD/DIF/DEA/J 指标

### trade_records - 交易记录
- trace_id, trade_id, side, action, entry/exit_price, contracts, pnl

### position_records - 持仓记录
- position_id, entry/exit_price, status(OPEN/CLOSED), exit_reason

## 交易参数 (config.py)

### V5 T0 参数
- T0_HIST15_LIMIT, T0_DIF15_LIMIT
- T0_J15M_LIMIT / T0_J15M_LIMIT_KONG

### 均值参数
- MEANS_HIST15_COUNT / HIST15_MEANS_LIMIT
- MEANS_DIF15_COUNT / DIF15_MEANS_LIMIT

### 止损止盈
- STOP_LOSS_POINTS: 止损点数
- TP_LEVELS: 止盈级别 [1.006, 1.012, 1.018, 1.024, 1.03]
- DRAWDOWN_POINTS: 回撤触发点数

### 交易模式
- OPEN_TAKER_OR_MAKER: TAKER/MAKER
- MAKER_FEE_RATE / TAKER_FEE_RATE
- LEVERAGE: 杠杆倍数

## Web API

### 页面
- `/` - K线图 (kline_chart.html)
- `/params` - 交易参数 (trade_params.html)

### API
- `GET /api/kline` - K线数据
- `GET /api/trades` - 交易记录
- `GET /api/positions` - 持仓记录
- `GET /api/config` - 交易参数

## 启动流程

```bash
# 1. K线同步
python data/realtime_kline_sync.py

# 2. 指标计算
python data/sync_macd_indicators.py

# 3. 启动交易
python data/db_driven_trading.py

# 4. Web服务
python web/kline_viewer.py

# 5. 历史数据同步（可选，按需运行）
python scripts/sync_trades_from_binance.py --year 2026
```

**说明**：
- **步骤1-4** 是正常交易运行的必需步骤，需要同时保持运行
- **步骤5** `sync_trades_from_binance` **不需要**与 `db_driven_trading` 同时运行
  - 用途：历史数据补全、数据一致性校验、修复遗漏记录
  - 运行时机：首次部署时同步历史数据，或发现数据不一致时手动修复

## 交易记录流程

### 完整交易数据流

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          数据驱动交易流程                                 │
└─────────────────────────────────────────────────────────────────────────┘

  币安交易所(WebSocket)
           │
           ▼
  ┌─────────────────────┐
  │ realtime_kline_sync │  ◀── 实时获取K线，写入 klines_1m
  └──────────┬──────────┘
             │
             ▼
  ┌─────────────────────┐
  │ sync_macd_indicators│  ◀── 计算MACD指标，写入 klines_1m_macd_smooth_ma
  └──────────┬──────────┘
             │
             ▼
  ┌─────────────────────┐     ┌──────────────────┐
  │ db_driven_trading   │────▶│ SignalCalculator │  ◀── V5策略信号计算
  └──────────┬──────────┘     └──────────────────┘
             │
             ▼
  ┌─────────────────────┐     ┌──────────────────┐
  │ TradeEngine         │────▶│ 币安交易所下单    │
  │ - process_tick()    │     │ (BINANCE_TESTNET │
  │ - open_position()   │     │  / binance_live) │
  │ - close_position()  │     └──────────────────┘
  └──────────┬──────────┘
             │
    ┌────────┴────────┐
    ▼                 ▼
┌──────────┐    ┌──────────┐
│开仓记录  │    │平仓记录  │
│- OPEN    │    │- TP      │
│          │    │- SL      │
│          │    │- DRAWDOWN│
│          │    │- TIMEOUT │
└────┬─────┘    └────┬─────┘
     │               │
     └───────┬───────┘
             ▼
  ┌─────────────────────┐
  │  TradeRecorder      │  ◀── 统一交易记录器 (单例模式)
  │  (core/trade_recorder)│
  └──────────┬──────────┘
             │
    ┌────────┴────────┐
    ▼                 ▼
┌──────────┐    ┌──────────┐
│trade_    │    │position_ │
│records   │    │records   │
│(交易明细) │    │(持仓记录) │
└──────────┘    └──────────┘
```

### TradeRecorder 使用方式

```python
from core.trade_recorder import get_trade_recorder, TradeRecord, PositionRecord

# 获取单例实例
trade_recorder = get_trade_recorder()

# 记录开仓
position_record = PositionRecord(
    position_id=pos.id,
    trace_id=trace_id,
    symbol=config.SYMBOL,
    side=side,
    entry_price=actual_price,
    entry_contracts=filled_contracts,
    open_time=ts.isoformat(),
    status='OPEN',
    entry_order_id=str(order.order_id)
)
trade_recorder.record_position_open(position_record)

# 记录交易
trade_record = TradeRecord(
    trace_id=trace_id,
    trade_id=str(order.order_id),
    symbol=config.SYMBOL,
    side=side,
    action='OPEN',  # OPEN/CLOSE/TP/SL/DRAWDOWN/TIMEOUT
    entry_price=actual_price,
    contracts=filled_contracts,
    position_id=pos.id,
    order_id=str(order.order_id),
    fee_rate=open_fee_rate,
    fee_usd=open_fee_btc * actual_price,
    source='trade_engine',  # trade_engine/exchange_api/manual/sync
    trade_time=ts.isoformat(),
    notes=f"开仓信号: {signal_name}"
)
trade_recorder.record_trade(trade_record)
```

### 数据源标识 (source 字段)

| source | 说明 | 来源 |
|--------|------|------|
| `trade_engine` | 自动交易引擎 | db_driven_trading.py |
| `exchange_api` | 币安API同步 | sync_trades_from_binance.py |
| `manual` | 手动交易 | 手动录入 |
| `sync` | 数据同步 | 其他同步脚本 |

## 交易同步说明

### 本地与币安数据一致性

```
┌─────────────────────────────────────────────────────────┐
│                    数据一致性保障                        │
└─────────────────────────────────────────────────────────┘

  币安交易所
     │
     ├──▶ TradeEngine ──▶ trade_records (source='trade_engine')
     │                         │
     │                         ▼
     │                    实时监控交易
     │                         │
     │                    ┌────┴────┐
     │                    ▼         ▼
     │                 正常       异常(漏单)
     │                    │         │
     │                    │    ┌────┘
     │                    │    ▼
     │                    │  sync_trades_from_binance.py
     │                    │    (source='exchange_api')
     │                    │    │
     └────────────────────┴────┤
                              ▼
                    ┌─────────────────┐
                    │  合并交易记录    │
                    │  (trace_id关联) │
                    └─────────────────┘
```

### 同步策略

| 场景 | 处理方式 | 脚本 | 是否必需 |
|------|----------|------|----------|
| **实时交易** | TradeEngine自动记录 | db_driven_trading.py | **是** |
| **历史补全** | 按年批量同步 | sync_trades_from_binance.py --year 2026 | 否 |
| **断点续传** | 从上次同步时间继续 | sync_trades_from_binance.py (自动) | 否 |
| **定时同步** | 每5分钟同步最近1小时 | sync_trades_from_binance.py --daemon | 否 |

**注意**：`sync_trades_from_binance.py` 是辅助工具，用于：
1. 首次部署时同步历史成交记录
2. 怀疑有遗漏记录时进行数据校验和补全
3. 不需要与主交易程序同时运行

### 同步命令

```bash
# 同步最近24小时（同时同步持仓和交易记录）
python scripts/sync_trades_from_binance.py

# 同步指定年份
python scripts/sync_trades_from_binance.py --year 2026

# 仅同步持仓信息
python scripts/sync_trades_from_binance.py --sync-positions

# 后台自动同步模式
python scripts/sync_trades_from_binance.py --daemon --interval 5

# 查看同步汇总
python scripts/sync_trades_from_binance.py --summary

# 强制全量同步（忽略断点）
python scripts/sync_trades_from_binance.py --force-full

# 指定交易所类型
python scripts/sync_trades_from_binance.py --testnet  # 模拟盘
python scripts/sync_trades_from_binance.py --live     # 正式盘
```

### 持仓同步说明

同步脚本现在同时支持**持仓同步**和**交易记录同步**：

| 同步类型 | 说明 | 命令 |
|----------|------|------|
| **完整同步** | 同步持仓 + 交易记录 | `sync_trades_from_binance.py` |
| **仅持仓** | 只同步当前持仓状态 | `--sync-positions` |
| **仅交易** | 只同步历史成交记录 | 默认行为（无需额外参数） |

**持仓同步逻辑**：
1. 从币安获取当前持仓信息
2. 对比本地数据库中的持仓记录
3. 新增、更新或关闭本地持仓记录
4. 当币安账户无持仓时，自动关闭本地所有未平仓记录

### 断点续传

- 状态文件: `data/.sync_state.json`
- 记录字段: `last_sync_time`, `last_sync_count`, `total_synced`
- 自动回退: 续传时回退1小时确保不遗漏数据
