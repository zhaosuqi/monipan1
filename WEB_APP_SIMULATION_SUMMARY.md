# Web App 模拟盘功能实现总结

## 修改概述

已成功将 `web_app.py` 扩展为支持三种模式的统一Web监控服务：
- **回测模式** (backtest) - 从数据库读取历史数据
- **模拟盘模式** (simulation) - 连接币安测试网实时交易
- **实盘模式** (live) - 连接币安实盘实时交易

## 主要修改

### 1. 环境变量加载顺序 (web_app.py:16-30)

```python
from dotenv import load_dotenv

# 必须在导入其他模块之前加载环境变量
load_dotenv()
```

**原因**: 确保config模块初始化前已加载.env配置

### 2. 实时数据和线程管理 (web_app.py:54-62)

```python
live_data = {
    'exchange': None,              # 交易所实例
    'trade_engine': None,          # 交易引擎
    'klines_buffer': [],           # K线缓冲区
    'thread': None,                # 后台线程
    'stop_event': threading.Event(), # 停止信号
    'latest_kline': None           # 最新K线
}
```

### 3. K线API增强 (web_app.py:446-562)

修改 `/api/klines` 接口，支持三种数据源：

```python
@app.route('/api/klines', methods=['GET'])
def get_klines():
    current_mode = get_current_mode()

    if current_mode in ['simulation', 'live']:
        # 从交易所或缓冲区获取实时数据
        if live_data['klines_buffer']:
            klines = live_data['klines_buffer'][-limit:]
        elif live_data['exchange']:
            klines = live_data['exchange'].get_klines(...)
    else:  # backtest
        # 从数据库读取历史数据
        reader = DbKlineReader(...)
```

### 4. 实时交易启动逻辑 (web_app.py:369-384)

```python
elif current_mode in ['live', 'simulation']:
    bot_state['running'] = True
    bot_state['mode'] = current_mode
    bot_state['start_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 启动实时交易线程
    live_thread = threading.Thread(target=run_live_trading_worker, daemon=True)
    live_thread.start()
```

### 5. 实时交易工作线程 (web_app.py:1149-1296)

新增 `run_live_trading_worker()` 函数，实现：

1. 连接到币安API
2. 预加载1000条历史K线
3. 启动60秒轮询获取最新K线
4. 调用TradeEngine处理交易信号
5. 通过WebSocket推送数据到前端

```python
def run_live_trading_worker():
    # 连接交易所
    live_data['exchange'] = create_exchange()
    live_data['exchange'].connect()

    # 创建交易引擎
    live_data['trade_engine'] = TradeEngine()

    # 预加载历史数据
    historical_klines = live_data['exchange'].get_klines(limit=1000)
    live_data['klines_buffer'].extend(historical_klines)

    # 实时K线循环
    while not stop_event.is_set():
        klines = live_data['exchange'].get_klines(limit=1)
        # 处理新K线...
        live_data['trade_engine'].process_tick(...)
        socketio.emit('new_kline', kline_data)
        time.sleep(60)
```

### 6. 停止逻辑增强 (web_app.py:403-437)

```python
@app.route('/api/bot/stop', methods=['POST'])
def stop_bot():
    if bot_state['mode'] in ['simulation', 'live']:
        live_data['stop_event'].set()  # 发送停止信号到实时线程

    bot_state['running'] = False
    bot_state['connected'] = False
```

## 新增文件

### 1. start_web_monitor.sh

统一的Web监控启动脚本，自动检测当前模式并启动服务。

```bash
#!/bin/bash
# 检查模式
if [ "$BINANCE_TESTNET" = "1" ]; then
    echo "模拟盘模式"
elif [ "$DB_SIM_MODE" = "1" ]; then
    echo "回测模式"
fi

# 启动服务
python web_app.py
```

### 2. WEB_MONITOR_GUIDE.md

完整的使用指南，包括：
- 三种模式对比
- 快速开始教程
- 模式切换方法
- API接口文档
- 故障排查指南
- 生产部署建议

## WebSocket事件

模拟盘模式下支持以下事件：

| 事件 | 方向 | 说明 |
|------|------|------|
| `historical_klines_loaded` | 服务器→客户端 | 历史K线加载完成 |
| `new_kline` | 服务器→客户端 | 新K线数据（每分钟） |
| `bot_state_changed` | 服务器→客户端 | 机器人状态变化 |
| `trade_signal` | 服务器→客户端 | 交易信号 |

## 使用方式

### 方式1: 使用启动脚本（推荐）

```bash
# 1. 切换到模拟盘
./switch_to_testnet.sh

# 2. 配置API密钥
vim .env  # 填入 BINANCE_API_KEY 和 BINANCE_API_SECRET

# 3. 启动Web监控
./start_web_monitor.sh

# 4. 访问监控页面
# http://localhost:8076/monitor
```

### 方式2: 直接运行

```bash
python web_app.py --debug  # 开发模式，支持热重载
```

### 方式3: 通过Web界面切换

1. 访问 http://localhost:8076/config
2. 点击"切换到模拟盘模式"
3. 系统自动更新配置并重启
4. 回到监控页面启动机器人

## 技术特点

### 1. 统一接口

- 同一套Web界面支持三种模式
- 相同的API接口
- 无需学习不同的使用方式

### 2. 自动切换

- 根据环境变量自动检测模式
- 数据源自动选择（数据库 vs API）
- 智能缓存管理

### 3. 实时推送

- WebSocket实时数据推送
- 前端自动更新图表
- 无需手动刷新

### 4. 线程安全

- 使用 `threading.Event` 实现优雅停止
- 独立的后台线程处理实时数据
- 避免阻塞主线程

## 与 live_web_app.py 的区别

| 特性 | live_web_app.py | web_app.py (现在) |
|------|-----------------|-------------------|
| 模式支持 | 仅模拟盘 | 三种模式 |
| 配置管理 | 无 | 完整的配置页面 |
| 参数调整 | 无 | 参数维护页面 |
| 回测功能 | 无 | 支持数据库回测 |
| 会话模式 | 无 | 支持会话划分回测 |
| 统一监控 | 无 | 统一的监控界面 |

**建议**: 删除 `live_web_app.py`，统一使用 `web_app.py`

## 测试验证

### 启动测试

```bash
$ python web_app.py
2026-01-09 00:47:41 - __main__ - INFO - 启动Web监控服务
2026-01-09 00:47:41 - __main__ - INFO - 访问地址: http://0.0.0.0:8076
✓ 成功启动
```

### 模式测试

```bash
$ curl http://localhost:8076/api/config/mode
{
  "success": true,
  "data": {
    "mode": "simulation",
    "mode_name": "模拟盘模式"
  }
}
```

## 下一步优化建议

1. **信号计算增强**
   - 在实时模式中集成SignalCalculator
   - 支持实时指标计算（MACD, KDJ等）

2. **告警通知**
   - 集成飞书webhook
   - 交易信号推送
   - 异常情况告警

3. **性能优化**
   - K线数据缓存
   - 数据库连接池
   - 异步处理

4. **监控增强**
   - 账户余额实时显示
   - 持仓信息展示
   - PnL实时计算

## 相关文件清单

- `web_app.py` - 主程序（已修改）
- `start_web_monitor.sh` - 启动脚本（新增）
- `WEB_MONITOR_GUIDE.md` - 使用指南（新增）
- `.env` - 环境变量配置
- `exchange_layer/` - 交易所接口
- `trade_module/trade_engine.py` - 交易引擎

## 总结

✅ 成功将 `web_app.py` 扩展为支持模拟盘模式
✅ 无需单独的 `live_web_app.py`
✅ 统一的界面和API支持三种模式
✅ 实时数据推送和交易执行
✅ 完整的文档和使用指南

现在可以通过 `./start_web_monitor.sh` 启动统一的Web监控服务，自动根据当前配置选择回测或模拟盘模式！
