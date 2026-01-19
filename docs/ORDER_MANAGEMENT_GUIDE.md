# 订单管理功能说明

## 概述

交易所接口层现在支持完整的订单管理功能，包括：
1. **下单** - 市价单和限价单
2. **取消订单** - 取消单个订单或所有订单
3. **修改订单** - 修改订单价格和数量
4. **查询订单** - 查询单个订单或所有挂单

## 核心特性

### 1. 基于K线的智能成交判断

限价单的成交判断基于最近5分钟K线数据：

**买单成交逻辑**：
- 如果订单价格 >= 5分钟最低价，则成交
- 成交价 = min(订单价, 当前价)

**卖单成交逻辑**：
- 如果订单价格 <= 5分钟最高价，则成交
- 成交价 = max(订单价, 当前价)

这种设计模拟了真实交易所的价格撮合机制。

### 2. 市价单

市价单立即成交，使用最新K线的收盘价作为成交价。

```python
order = exchange.place_order(
    symbol='BTCUSD_PERP',
    side='BUY',
    order_type='MARKET',
    quantity=1.0
)

# 订单状态: FILLED
# 成交价格: 16531.10
# 成交数量: 1.0
```

### 3. 限价单

限价单创建后，系统会自动检查5分钟K线数据判断是否成交。

```python
order = exchange.place_order(
    symbol='BTCUSD_PERP',
    side='BUY',
    order_type='LIMIT',
    quantity=1.0,
    price=16530.0
)

# 如果 16530.0 >= 5分钟最低价，则订单成交
# 否则订单保持NEW状态（等待成交）
```

### 4. 取消订单

可以取消状态为NEW或PARTIALLY_FILLED的订单。

```python
success = exchange.cancel_order(
    symbol='BTCUSD_PERP',
    order_id='1000'
)

# 成功返回True，订单状态变为CANCELED
# 失败返回False（订单不存在或已成交）
```

### 5. 修改订单

可以修改未成交订单的价格和数量。

```python
success = exchange.modify_order(
    symbol='BTCUSD_PERP',
    order_id='1000',
    quantity=2.0,  # 新数量（可选）
    price=16540.0   # 新价格（可选）
)

# 修改成功后会重新检查成交条件
```

### 6. 查询订单

```python
# 查询单个订单
order = exchange.get_order('BTCUSD_PERP', '1000')

# 查询所有挂单
open_orders = exchange.get_open_orders('BTCUSD_PERP')
```

## API接口说明

### BaseExchange 接口

```python
class BaseExchange:
    # 下单
    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        client_order_id: Optional[str] = None,
        **kwargs
    ) -> Order

    # 取消订单
    def cancel_order(self, symbol: str, order_id: str) -> bool

    # 修改订单
    def modify_order(
        self,
        symbol: str,
        order_id: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None
    ) -> bool

    # 取消所有订单
    def cancel_all_orders(self, symbol: str) -> int

    # 查询订单
    def get_order(self, symbol: str, order_id: str) -> Optional[Order]

    # 查询所有挂单
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]
```

## 订单状态

| 状态 | 说明 |
|-----|------|
| NEW | 新订单，等待成交 |
| PARTIALLY_FILLED | 部分成交 |
| FILLED | 完全成交 |
| CANCELED | 已取消 |
| REJECTED | 订单被拒绝 |
| EXPIRED | 订单已过期 |

## 使用示例

### 示例1: 完整的订单生命周期

```python
from exchange_layer import create_exchange, ExchangeType

exchange = create_exchange(ExchangeType.MOCK_LOCAL)
exchange.connect()

# 1. 下限价单
order = exchange.place_order(
    symbol='BTCUSD_PERP',
    side='BUY',
    order_type='LIMIT',
    quantity=1.0,
    price=16530.0
)
print(f"订单ID: {order.order_id}")
print(f"订单状态: {order.status.value}")

# 2. 如果未成交，修改价格
if order.status.value == 'NEW':
    exchange.modify_order(
        'BTCUSD_PERP',
        order.order_id,
        price=16525.0
    )

# 3. 查询订单状态
updated_order = exchange.get_order('BTCUSD_PERP', order.order_id)
print(f"更新后状态: {updated_order.status.value}")

# 4. 如果仍未成交，取消订单
if updated_order.status.value == 'NEW':
    exchange.cancel_order('BTCUSD_PERP', order.order_id)

exchange.disconnect()
```

### 示例2: 批量订单管理

```python
# 创建多个限价单
orders = []
for i in range(5):
    order = exchange.place_order(
        symbol='BTCUSD_PERP',
        side='BUY',
        order_type='LIMIT',
        quantity=1.0,
        price=16500 + i * 10
    )
    orders.append(order)

# 查询所有挂单
open_orders = exchange.get_open_orders('BTCUSD_PERP')
print(f"当前挂单数: {len(open_orders)}")

# 取消所有订单
count = exchange.cancel_all_orders('BTCUSD_PERP')
print(f"已取消 {count} 个订单")
```

### 示例3: HTTP API使用

如果启动了本地虚拟币安API服务器，可以通过HTTP接口管理订单：

```bash
# 启动服务器
./start_mock_server.sh

# 使用curl测试
curl -X POST http://127.0.0.1:8080/fapi/v1/order \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSD_PERP",
    "side": "BUY",
    "type": "LIMIT",
    "quantity": 1.0,
    "price": 16530.0
  }'

# 取消订单
curl -X DELETE "http://127.0.0.1:8080/fapi/v1/order?symbol=BTCUSD_PERP&orderId=1000"

# 修改订单
curl -X PUT http://127.0.0.1:8080/fapi/v1/order \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSD_PERP",
    "orderId": "1000",
    "price": 16535.0
  }'
```

## 测试

运行订单管理功能测试：

```bash
python3 test_order_management.py
```

测试内容：
- ✓ 市价单下单和立即成交
- ✓ 限价单基于5分钟K线成交
- ✓ 限价单不成交（保持NEW状态）
- ✓ 取消订单
- ✓ 修改订单价格和数量
- ✓ 查询订单和挂单列表

## 注意事项

### 1. 限价单成交判断

限价单的成交判断依赖于K线数据：
- 使用最近5条1分钟K线
- 判断最高价和最低价
- 市价单使用最新K线收盘价

### 2. 订单修改限制

- 只能修改状态为NEW或PARTIALLY_FILLED的订单
- 已成交或已取消的订单无法修改
- 修改后会重新检查成交条件

### 3. 币安API差异

币安API不支持直接修改订单，需要：
1. 查询原订单
2. 取消原订单
3. 创建新订单

`BinanceExchange.modify_order()` 自动处理这个流程。

### 4. 持仓更新

订单成交后会自动更新：
- 持仓数量和方向
- 平均入场价格
- 账户余额

## 文件变更

### 新增文件
- [test_order_management.py](test_order_management.py) - 订单管理测试脚本
- [docs/ORDER_MANAGEMENT_GUIDE.md](docs/ORDER_MANAGEMENT_GUIDE.md) - 本文档

### 修改文件
- [exchange_layer/base_exchange.py](exchange_layer/base_exchange.py) - 添加`modify_order()`抽象方法
- [exchange_layer/mock_exchange.py](exchange_layer/mock_exchange.py) - 实现订单管理功能
- [exchange_layer/binance_exchange.py](exchange_layer/binance_exchange.py) - 实现订单修改逻辑
- [exchange_layer/mock_server.py](exchange_layer/mock_server.py) - 添加订单修改HTTP接口

## 总结

订单管理功能现在完全支持：

✅ **市价单** - 立即成交
✅ **限价单** - 基于K线智能判断成交
✅ **取消订单** - 支持单个和批量取消
✅ **修改订单** - 修改价格和数量
✅ **查询订单** - 查询单个和所有挂单
✅ **HTTP API** - 兼容币安API格式
✅ **完整测试** - 6个测试全部通过

这些功能使得本地模拟交易所更加接近真实交易所的行为！
