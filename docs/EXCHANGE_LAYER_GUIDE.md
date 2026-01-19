# 交易所接口层使用指南

## 概述

交易所接口层提供了一个统一的API抽象，支持三种运行模式：

1. **本地数据库回测** (MOCK_LOCAL) - 从SQLite数据库读取历史K线数据进行回测
2. **本地虚拟币安API服务器** - 提供HTTP服务，模拟币安API接口
3. **币安官方虚拟盘/实盘** (BINANCE_TESTNET/BINANCE_LIVE) - 连接币安真实API

## 架构设计

```
┌─────────────────────────────────────────────┐
│          交易策略/回测系统                    │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│       exchange_layer (统一接口层)            │
│  ┌──────────────────────────────────────┐  │
│  │  BaseExchange (抽象基类)              │  │
│  └──────────────────────────────────────┘  │
│           ▼           ▼           ▼         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │  Mock    │ │ Binance  │ │  Mock    │   │
│  │ Exchange │ │ Exchange │ │  Server  │   │
│  └──────────┘ └──────────┘ └──────────┘   │
└─────────────────────────────────────────────┘
        ▼               ▼               ▼
  ┌─────────┐    ┌─────────┐    ┌─────────┐
  │ SQLite  │    │Binance  │    │ HTTP    │
  │ 数据库  │    │ API     │    │ API     │
  └─────────┘    └─────────┘    └─────────┘
```

## 快速开始

### 1. 本地数据库回测

```python
from exchange_layer import create_exchange, ExchangeType
from datetime import datetime

# 创建本地模拟交易所
exchange = create_exchange(ExchangeType.MOCK_LOCAL)
exchange.connect()

# 获取K线数据
klines = exchange.get_klines(
    symbol='BTCUSD_PERP',
    interval='1m',
    limit=100,
    start_time=datetime(2024, 1, 1),
    end_time=datetime(2024, 1, 2)
)

# 下单（模拟）
order = exchange.place_order(
    symbol='BTCUSD_PERP',
    side='BUY',
    order_type='MARKET',
    quantity=1.0
)

print(f"订单状态: {order.status.value}")
print(f"成交价格: {order.avg_price}")

# 查询账户
account = exchange.get_account_info()
print(f"账户余额: {account.total_wallet_balance:.2f} USDT")

exchange.disconnect()
```

### 2. 连接币安测试网

```python
from exchange_layer import create_exchange, ExchangeType
from core.config import config

# 确保已配置API密钥
# export BINANCE_API_KEY=your_api_key
# export BINANCE_API_SECRET=your_api_secret
# export BINANCE_TESTNET=1

exchange = create_exchange(ExchangeType.BINANCE_TESTNET)
exchange.connect()

# 获取最新K线
klines = exchange.get_klines(
    symbol=config.SYMBOL,
    interval=config.KLINE_INTERVAL,
    limit=10
)

# 查询账户
account = exchange.get_account_info()
print(f"账户余额: {account.total_wallet_balance:.2f} USDT")

# 查询持仓
position = exchange.get_position(config.SYMBOL)
if position:
    print(f"持仓: {position['side']} {position['position_amount']}")

exchange.disconnect()
```

### 3. 自动检测交易所类型

```python
from exchange_layer import create_exchange

# 不指定类型，根据配置自动检测
# REPLAY_MODE=1 或 DB_SIM_MODE=1 -> MOCK_LOCAL
# BINANCE_TESTNET=1 -> BINANCE_TESTNET
# 否则 -> BINANCE_LIVE

exchange = create_exchange()  # 自动检测
exchange.connect()

# 获取K线
klines = exchange.get_klines('BTCUSD_PERP', '1m', limit=100)
```

### 4. 启动本地虚拟币安API服务器

```bash
# 方式1: 使用启动脚本
./start_mock_server.sh

# 方式2: 直接运行Python模块
python3 -m exchange_layer.mock_server \
    --host 127.0.0.1 \
    --port 8080 \
    --db-path ./data/klines.db \
    --table klines_1m
```

服务器启动后，外部工具可以通过以下接口访问：

- **K线接口**: `GET http://127.0.0.1:8080/fapi/v1/klines`
- **下单接口**: `POST http://127.0.0.1:8080/fapi/v1/order`
- **取消订单**: `DELETE http://127.0.0.1:8080/fapi/v1/order`
- **查询订单**: `GET http://127.0.0.1:8080/fapi/v1/order`
- **账户信息**: `GET http://127.0.0.1:8080/fapi/v2/account`

## 配置说明

### 环境变量配置

```bash
# === 基础配置 ===
# 交易所类型（可选，如果不设置则自动检测）
export EXCHANGE_TYPE=mock_local  # 或 binance_testnet, binance_live

# === 数据库配置（本地回测） ===
export DB_PATH=./data/klines.db
export HIST_TABLE=klines_1m
export REPLAY_MODE=1
export DB_SIM_MODE=1

# === 币安API配置（测试网/实盘） ===
export BINANCE_API_KEY=your_api_key
export BINANCE_API_SECRET=your_api_secret
export BINANCE_TESTNET=1  # 1=测试网, 0=实盘

# === 本地虚拟服务器配置 ===
export MOCK_SERVER_HOST=127.0.0.1
export MOCK_SERVER_PORT=8080
export MOCK_SERVER_ENABLED=0
```

### 配置文件方式

在 `config.json` 中添加：

```json
{
  "EXCHANGE_TYPE": "mock_local",
  "BINANCE_TESTNET": 1,
  "REPLAY_MODE": 1,
  "MOCK_SERVER_HOST": "127.0.0.1",
  "MOCK_SERVER_PORT": 8080
}
```

## API接口说明

### BaseExchange 基础接口

所有交易所实现都继承自 `BaseExchange`，提供统一的接口：

#### 1. 连接管理

```python
exchange.connect()      # 连接到交易所
exchange.disconnect()   # 断开连接
exchange.is_connected() # 检查连接状态
```

#### 2. K线数据

```python
klines = exchange.get_klines(
    symbol='BTCUSD_PERP',    # 交易对
    interval='1m',           # 时间周期: 1m, 5m, 15m, 1h, 4h, 1d
    limit=1000,              # 数量限制
    start_time=datetime(2024, 1, 1),  # 开始时间（可选）
    end_time=datetime(2024, 1, 2)     # 结束时间（可选）
)
```

#### 3. 订单操作

```python
# 下单
order = exchange.place_order(
    symbol='BTCUSD_PERP',
    side='BUY',              # BUY/SELL
    order_type='MARKET',     # MARKET/LIMIT/STOP_MARKET/STOP_LIMIT
    quantity=1.0,            # 数量
    price=43000.0,           # 价格（限价单必需）
    stop_price=42000.0,      # 止损价（止损单必需）
    client_order_id='client_123'  # 客户端订单ID（可选）
)

# 取消订单
exchange.cancel_order('BTCUSD_PERP', order_id)

# 取消所有订单
count = exchange.cancel_all_orders('BTCUSD_PERP')

# 查询订单
order = exchange.get_order('BTCUSD_PERP', order_id)

# 查询所有挂单
orders = exchange.get_open_orders('BTCUSD_PERP')
```

#### 4. 账户和持仓

```python
# 获取账户信息
account = exchange.get_account_info()
print(f"总余额: {account.total_wallet_balance}")
print(f"可用余额: {account.available_balance}")
print(f"未实现盈亏: {account.unrealized_pnl}")

# 获取持仓
position = exchange.get_position('BTCUSD_PERP')
if position:
    print(f"持仓方向: {position['side']}")
    print(f"持仓数量: {position['position_amount']}")
    print(f"入场价格: {position['entry_price']}")
```

## 使用场景

### 场景1: 策略回测

```python
from exchange_layer import create_exchange, ExchangeType

# 使用本地数据库
exchange = create_exchange(ExchangeType.MOCK_LOCAL)
exchange.connect()

# 获取历史数据
klines = exchange.get_klines(
    symbol='BTCUSD_PERP',
    interval='1m',
    start_time=datetime(2024, 1, 1),
    end_time=datetime(2024, 1, 31)
)

# 运行策略回测
for kline in klines:
    # 策略逻辑...
    # 使用模拟订单测试
    order = exchange.place_order(...)
```

### 场景2: 本地虚拟盘测试

```bash
# 终端1: 启动本地虚拟币安API服务器
./start_mock_server.sh

# 终端2: 修改现有工具的BASE_URL连接到本地服务器
export BINANCE_BASE_URL=http://127.0.0.1:8080

# 运行交易工具（无需修改代码）
python your_trading_bot.py
```

### 场景3: 切换测试网和实盘

```python
from exchange_layer import switch_exchange, ExchangeType

# 开发阶段：使用本地回测
switch_exchange(ExchangeType.MOCK_LOCAL)

# 测试阶段：切换到币安测试网
switch_exchange(ExchangeType.BINANCE_TESTNET)

# 生产阶段：切换到币安实盘
switch_exchange(ExchangeType.BINANCE_LIVE)
```

## 测试

运行测试脚本验证功能：

```bash
# 测试交易所接口层
python3 test_exchange_layer.py

# 查看使用示例
python3 examples/exchange_usage_example.py
```

## 文件结构

```
exchange_layer/
├── __init__.py              # 导出接口
├── base_exchange.py         # 基础抽象类
├── binance_exchange.py      # 币安实现
├── mock_exchange.py         # 本地模拟实现
├── mock_server.py           # HTTP服务器
├── exchange_factory.py      # 工厂类
└── models.py                # 数据模型

examples/
└── exchange_usage_example.py  # 使用示例

test_exchange_layer.py        # 测试脚本
start_mock_server.sh          # 启动脚本
```

## 注意事项

1. **本地数据库回测**：
   - 需要预先创建SQLite数据库并导入K线数据
   - 订单是模拟的，不会实际执行
   - 适合策略开发和验证

2. **本地虚拟币安API服务器**：
   - 提供HTTP接口，兼容币安API格式
   - 可以让其他工具连接，无需修改代码
   - 使用Flask实现，需要安装Flask依赖

3. **币安测试网**：
   - 需要注册测试网账号并获取API密钥
   - 订单会实际执行，但使用虚拟资金
   - 适合策略测试和验证

4. **币安实盘**：
   - 使用真实资金，谨慎操作
   - 建议先在测试网充分验证
   - 注意风险控制

## 常见问题

### Q: 如何在现有代码中使用新的接口层？

A: 替换原有的交易所调用：

```python
# 旧代码
from binance.cm_futures import CMFutures
client = CMFutures(key=..., secret=...)
klines = client.klines(...)

# 新代码
from exchange_layer import create_exchange
exchange = create_exchange()
exchange.connect()
klines = exchange.get_klines(...)
```

### Q: 本地虚拟服务器支持哪些币安API接口？

A: 目前支持主要接口：
- K线数据: `/fapi/v1/klines`
- 下单: `/fapi/v1/order`
- 取消订单: `/fapi/v1/order`
- 查询订单: `/fapi/v1/order`
- 挂单列表: `/fapi/v1/openOrders`
- 账户信息: `/fapi/v2/account`
- 持仓信息: `/fapi/v2/positionRisk`

### Q: 如何添加自定义的交易所实现？

A: 继承 `BaseExchange` 并实现所有抽象方法：

```python
from exchange_layer import BaseExchange

class MyExchange(BaseExchange):
    def connect(self):
        # 实现连接逻辑
        pass

    def get_klines(self, ...):
        # 实现获取K线逻辑
        pass

    # 实现其他抽象方法...
```

## 更新日志

- **v1.0** (2024-01-07): 初始版本
  - 支持本地数据库回测
  - 支持币安测试网和实盘
  - 提供本地虚拟币安API服务器
  - 统一的接口抽象
