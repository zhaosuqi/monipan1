# Mock服务器启动和使用指南

## 什么是Mock服务器

Mock服务器是一个本地HTTP服务，模拟币安API接口，提供：
- K线数据查询接口
- 订单下单、取消、修改接口
- 账户和持仓查询接口
- 完全兼容币安API格式

外部工具只需修改 `BASE_URL` 即可连接到此服务器，无需修改任何业务代码。

## 启动方式

### 方式1: 使用启动脚本（推荐）

```bash
# 基础版本（需要确保conda环境）
./start_mock_server.sh

# 使用bigtree环境（推荐）
./start_mock_server_bigtree.sh
```

### 方式2: 手动启动

```bash
# 激活conda环境
source /Users/zhaosuqi/miniforge3/bin/activate bigtree

# 启动服务器
python3 -m exchange_layer.mock_server \
    --host 127.0.0.1 \
    --port 8080 \
    --db-path ./data/klines.db \
    --table klines_1m
```

### 方式3: 后台运行

```bash
# 后台启动
source /Users/zhaosuqi/miniforge3/bin/activate bigtree
nohup python3 -m exchange_layer.mock_server \
    --host 127.0.0.1 \
    --port 8080 \
    --db-path ./data/klines.db \
    --table klines_1m \
    > mock_server.log 2>&1 &

# 查看日志
tail -f mock_server.log

# 停止服务
pkill -f "mock_server"
```

## 配置参数

### 命令行参数

| 参数 | 说明 | 默认值 |
|-----|------|--------|
| `--host` | 监听地址 | 127.0.0.1 |
| `--port` | 监听端口 | 8080 |
| `--db-path` | 数据库路径 | ./data/klines.db |
| `--table` | 数据表名 | klines_1m |

### 环境变量配置

```bash
# 服务器配置
export MOCK_SERVER_HOST=127.0.0.1
export MOCK_SERVER_PORT=8080
export MOCK_SERVER_ENABLED=1

# 数据库配置
export HIST_DB_PATH=./data/klines.db
export HIST_TABLE=klines_1m
```

## API接口

服务器启动后，提供以下HTTP接口（兼容币安API格式）：

### 1. 健康检查

```bash
curl http://127.0.0.1:8080/health
```

**响应**：
```json
{
  "status": "ok",
  "exchange": "mock_binance_server",
  "connected": true
}
```

### 2. 获取K线数据

```bash
curl "http://127.0.0.1:8080/fapi/v1/klines?symbol=BTCUSD_PERP&interval=1m&limit=10"
```

**响应**：
```json
[
  [
    1672531200000,  # open_time
    "16531.10",     # open
    "16531.20",     # high
    "16521.60",     # low
    "16521.70",     # close
    "1234.56",      # volume
    1672531259999,  # close_time
    "20456789.12",  # quote_volume
    12345,          # trades
    "617.89",       # taker_buy_base
    "10234567.89",  # taker_buy_quote
    0               # ignore
  ]
]
```

### 3. 下单

```bash
curl -X POST http://127.0.0.1:8080/fapi/v1/order \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSD_PERP",
    "side": "BUY",
    "type": "MARKET",
    "quantity": 1.0
  }'
```

**响应**：
```json
{
  "orderId": "1000",
  "clientOrderId": "mock_abc123",
  "symbol": "BTCUSD_PERP",
  "side": "BUY",
  "type": "MARKET",
  "status": "FILLED",
  "price": 0,
  "origQty": 1.0,
  "executedQty": 1.0,
  "avgPrice": 16531.1
}
```

### 4. 取消订单

```bash
curl -X DELETE "http://127.0.0.1:8080/fapi/v1/order?symbol=BTCUSD_PERP&orderId=1000"
```

### 5. 修改订单

```bash
curl -X PUT http://127.0.0.1:8080/fapi/v1/order \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSD_PERP",
    "orderId": "1000",
    "price": 16540.0,
    "quantity": 2.0
  }'
```

### 6. 查询订单

```bash
curl "http://127.0.0.1:8080/fapi/v1/order?symbol=BTCUSD_PERP&orderId=1000"
```

### 7. 查询挂单

```bash
curl "http://127.0.0.1:8080/fapi/v1/openOrders?symbol=BTCUSD_PERP"
```

### 8. 账户信息

```bash
curl http://127.0.0.1:8080/fapi/v2/account
```

**响应**：
```json
{
  "totalWalletBalance": 10000.0,
  "availableBalance": 10000.0,
  "totalUnrealizedProfit": 0.0
}
```

### 9. 持仓信息

```bash
curl "http://127.0.0.1:8080/fapi/v2/positionRisk?symbol=BTCUSD_PERP"
```

### 10. 交易所信息

```bash
curl http://127.0.0.1:8080/fapi/v1/exchangeInfo
```

## 客户端连接

### Python客户端（使用binance-connector）

```python
from binance.cm_futures import CMFutures

# 创建客户端，设置自定义BASE_URL
client = CMFutures()
client.base_url = 'http://127.0.0.1:8080'  # 指向Mock服务器

# 获取K线
klines = client.klines(symbol='BTCUSD_PERP', interval='1m', limit=10)
print(klines)

# 下单
order = client.new_order(
    symbol='BTCUSD_PERP',
    side='BUY',
    type='MARKET',
    quantity=1.0
)
print(order)
```

### Python客户端（使用exchange_layer）

```python
from exchange_layer import create_exchange, ExchangeType

# 创建MockExchange
exchange = create_exchange(ExchangeType.MOCK_LOCAL)
exchange.connect()

# 获取K线
klines = exchange.get_klines('BTCUSD_PERP', '1m', limit=10)

# 下单
order = exchange.place_order(
    symbol='BTCUSD_PERP',
    side='BUY',
    order_type='MARKET',
    quantity=1.0
)

# 查询账户
account = exchange.get_account_info()
print(f"余额: {account.total_wallet_balance}")

exchange.disconnect()
```

### curl命令

参见上面的API接口示例。

## 测试服务器

### 快速测试

```bash
# 1. 健康检查
curl http://127.0.0.1:8080/health

# 2. 获取K线
curl "http://127.0.0.1:8080/fapi/v1/klines?symbol=BTCUSD_PERP&interval=1m&limit=5"

# 3. 下单
curl -X POST http://127.0.0.1:8080/fapi/v1/order \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTCUSD_PERP","side":"BUY","type":"MARKET","quantity":1.0}'

# 4. 查询账户
curl http://127.0.0.1:8080/fapi/v2/account
```

### 使用测试脚本

```bash
# 测试交易所接口
python3 test_exchange_layer.py

# 测试订单管理
python3 test_order_management.py

# 测试回测流程
python3 test_backtest_with_mock.py
```

## 停止服务器

### 方式1: 使用pkill

```bash
pkill -f "mock_server"
```

### 方式2: 查找进程并kill

```bash
# 查找进程
ps aux | grep mock_server

# 杀死进程
kill <PID>
```

### 方式3: 如果在终端运行

直接按 `Ctrl+C` 停止。

## 常见问题

### 1. 端口被占用

**错误**：`Address already in use`

**解决**：
```bash
# 查找占用端口的进程
lsof -i :8080

# 杀死进程
kill -9 <PID>

# 或者使用其他端口
python3 -m exchange_layer.mock_server --port 8081
```

### 2. 数据库不存在

**错误**：`数据库文件不存在`

**解决**：
```bash
# 确保数据库文件存在
ls -lh ./data/klines.db

# 如果不存在，先创建并导入数据
python3 fetch_klines.py --days 365
```

### 3. ModuleNotFoundError

**错误**：`No module named 'binance.cm_futures'`

**解决**：
```bash
# 使用bigtree环境
source /Users/zhaosuqi/miniforge3/bin/activate bigtree

# 或安装依赖
pip install binance-connector flask
```

### 4. 连接拒绝

**错误**：`Connection refused`

**检查**：
```bash
# 1. 确认服务器正在运行
ps aux | grep mock_server

# 2. 确认端口正确
netstat -an | grep 8080

# 3. 测试连接
curl http://127.0.0.1:8080/health
```

## 高级用法

### 1. 日志记录

服务器会记录所有操作，可以通过日志查看：
```bash
# 查看日志（如果在终端运行）
# 直接查看终端输出

# 如果后台运行
tail -f mock_server.log
```

### 2. 自定义端口

```bash
# 使用8081端口
python3 -m exchange_layer.mock_server --port 8081

# 客户端连接时修改端口
curl http://127.0.0.1:8081/health
```

### 3. 监听所有网卡

```bash
# 监听0.0.0.0允许外部访问
python3 -m exchange_layer.mock_server --host 0.0.0.0

# 客户端使用实际IP
curl http://192.168.1.100:8080/health
```

### 4. 使用不同数据库

```bash
# 使用测试数据库
python3 -m exchange_layer.mock_server \
    --db-path ./data/test_klines.db \
    --table klines_5m
```

## 性能说明

- K线查询：从SQLite数据库读取，速度快
- 订单处理：内存中模拟，即时响应
- 并发支持：Flask开发服务器，适合测试和开发
- 生产环境：建议使用Gunicorn或uWSGI

## 总结

Mock服务器提供了完整的币安API模拟，让你可以：

✅ **本地测试** - 无需连接币安
✅ **快速迭代** - 立即成交，无需等待
✅ **零风险** - 使用虚拟资金
✅ **完全兼容** - 只需修改BASE_URL
✅ **真实模拟** - 基于真实历史数据

现在就启动服务器，开始测试吧！
