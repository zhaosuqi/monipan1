# K线图表买卖点标记功能

## 功能概述

在K线图表上实时显示买卖点标记,帮助用户直观地查看交易信号和开平仓位置。

## 实现效果

### 标记类型

1. **买入信号** - 绿色向上箭头 (↑)
   - 位置: K线下方
   - 颜色: `#26a69a` (绿色)
   - 文本: 显示买入价格

2. **卖出信号** - 红色向下箭头 (↓)
   - 位置: K线上方
   - 颜色: `#ef5350` (红色)
   - 文本: 显示卖出价格

3. **平仓标记** - 灰色圆点 (●)
   - 位置: K线上方
   - 颜色: `#999999` (灰色)
   - 文本: 显示平仓价格和盈亏 (PnL)

### 数据流

```
回测执行
  ↓
检测到交易信号(开仓/平仓)
  ↓
后端发送WebSocket事件: trade_signal
  ↓
前端接收信号并转换为标记格式
  ↓
添加到tradeMarkers数组
  ↓
调用 candleSeries.setMarkers() 更新图表
  ↓
图表上显示标记
```

## 修改的文件

### 1. 后端修改

#### web_app.py (run_backtest_worker)

**位置**: 第1199-1253行

**修改内容**:
```python
# 计算交易信号
signal = signal_calculator.calculate_open_signal(kline)

# 发送开仓信号到前端用于图表标记
if signal and signal.action == 'open':
    signal_type = 'buy' if signal.side == 'long' else 'sell'
    socketio.emit('trade_signal', {
        'type': signal_type,
        'timestamp': str(kline.get('open_time')),
        'price': float(kline.get('close', 0)),
        'side': signal.side
    })

# 记录处理前的持仓数量
positions_before = len(trade_engine.positions)

trade_engine.process_tick(...)

# 检测是否有平仓
positions_after = len(trade_engine.positions)
if positions_after < positions_before:
    if trade_engine.trades:
        last_trade = trade_engine.trades[-1]
        socketio.emit('trade_signal', {
            'type': 'close',
            'timestamp': str(last_trade.exit_time),
            'price': float(last_trade.exit_price),
            'side': last_trade.side,
            'pnl': float(last_trade.net_pnl)
        })
```

#### trade_module/backtest_session.py (run_session)

**位置**: 第307-360行

**修改内容**: 与上面类似,在会话回测模式中也发送交易信号

### 2. 前端修改

#### web/templates/monitor.html

**修改1: 添加变量 (第207-213行)**
```javascript
let klineChart = null;
let candleSeries = null;
let volumeSeries = null;
let markerSeries = null;  // 买卖点标记系列
let socket = null;
let botRunning = false;
let tradeMarkers = [];  // 存储所有买卖点标记
```

**修改2: 初始化时清空标记 (第303-305行)**
```javascript
// 清空标记数组
tradeMarkers = [];
console.log('✓ 交易标记已重置');
```

**修改3: 接收交易信号 (第401-433行)**
```javascript
socket.on('trade_signal', function(signal) {
    console.log('收到交易信号:', signal);

    // 转换时间戳
    let time;
    if (typeof signal.timestamp === 'string') {
        time = new Date(signal.timestamp).getTime() / 1000;
    } else {
        time = signal.timestamp;
    }

    // 添加到标记数组
    tradeMarkers.push({
        time: time,
        position: signal.type === 'buy' ? 'belowBar' : 'aboveBar',
        color: signal.type === 'buy' ? '#26a69a' :
               signal.type === 'sell' ? '#ef5350' :
               signal.type === 'close' ? '#999999' : '#ff9800',
        shape: signal.type === 'buy' ? 'arrowUp' :
               signal.type === 'sell' ? 'arrowDown' :
               signal.type === 'close' ? 'circle' : 'arrowUp',
        text: signal.type === 'buy' ? `买入 ${signal.price.toFixed(2)}` :
              signal.type === 'sell' ? `卖出 ${signal.price.toFixed(2)}` :
              `平仓 ${signal.price.toFixed(2)} (PnL: ${signal.pnl ? signal.pnl.toFixed(4) : 'N/A'})`
    });

    // 更新图表标记
    if (candleSeries) {
        candleSeries.setMarkers(tradeMarkers);
        console.log(`✓ 已添加${signal.type}标记, 当前共${tradeMarkers.length}个标记`);
    }
});
```

**修改4: 更新图表时重新应用标记 (第509-513行)**
```javascript
// 重新应用交易标记(如果有)
if (tradeMarkers.length > 0) {
    candleSeries.setMarkers(tradeMarkers);
    console.log(`✓ 已重新应用 ${tradeMarkers.length} 个交易标记`);
}
```

**修改5: 启动时清空标记 (第657-662行)**
```javascript
// 清空之前的交易标记
tradeMarkers = [];
if (candleSeries) {
    candleSeries.setMarkers([]);
}
console.log('✓ 已清空之前的交易标记');
```

## 使用方法

### 1. 启动回测

1. 访问 http://localhost:8076/monitor
2. 点击"启动"按钮
3. 系统自动清空之前的标记
4. 开始新的回测

### 2. 观察标记

回测过程中,实时显示:
- 绿色向上箭头: 买入点 (做多)
- 红色向下箭头: 卖出点 (做空)
- 灰色圆点: 平仓点 (显示盈亏)

### 3. 查看详细信息

鼠标悬停在标记上可以看到:
- 买入/卖出价格
- 平仓时的盈亏金额

## WebSocket事件格式

### trade_signal 事件

**开仓信号**:
```json
{
  "type": "buy",           // 或 "sell"
  "timestamp": "2026-01-06 12:34:56",
  "price": 43250.5,
  "side": "long"           // 或 "short"
}
```

**平仓信号**:
```json
{
  "type": "close",
  "timestamp": "2026-01-06 14:23:45",
  "price": 43380.2,
  "side": "long",
  "pnl": 0.001234          // 盈亏(BTC)
}
```

## 标记颜色方案

| 信号类型 | 颜色 | 形状 | 位置 | 说明 |
|---------|------|------|------|------|
| 买入 (long) | `#26a69a` | arrowUp | belowBar | 绿色向上箭头 |
| 卖出 (short) | `#ef5350` | arrowDown | aboveBar | 红色向下箭头 |
| 平仓 (close) | `#999999` | circle | aboveBar | 灰色圆点 |

## 调试方法

### 浏览器控制台

打开浏览器控制台(F12),查看日志:

**正常流程**:
```
✓ 交易标记已重置
✓ 已清空之前的交易标记
收到交易信号: {type: "buy", timestamp: "...", price: 43250.5, side: "long"}
✓ 已添加buy标记, 当前共1个标记
收到交易信号: {type: "close", timestamp: "...", price: 43380.2, side: "long", pnl: 0.001234}
✓ 已添加close标记, 当前共2个标记
```

**常见问题**:

1. **标记不显示**:
   - 检查 `tradeMarkers` 数组是否有数据
   - 检查 candleSeries 是否初始化成功
   - 查看是否有JavaScript错误

2. **标记位置错误**:
   - 检查时间戳转换是否正确
   - 确认K线数据和标记时间是否匹配

3. **标记重复**:
   - 确认启动时是否清空了 `tradeMarkers`
   - 检查是否有多次订阅WebSocket事件

## 性能优化

### 1. 批量更新

当前实现: 每收到一个信号立即更新图表
- 优点: 实时性好
- 缺点: 频繁DOM操作

优化方案: 可以累积多个信号后批量更新
```javascript
let pendingMarkers = [];
socket.on('trade_signal', function(signal) {
    pendingMarkers.push(signal);
    // 每10个信号或每秒更新一次
    if (pendingMarkers.length >= 10) {
        flushMarkers();
    }
});
```

### 2. 标记数量限制

如果标记太多(>1000),可以只保留最近的N个:
```javascript
if (tradeMarkers.length > 1000) {
    tradeMarkers = tradeMarkers.slice(-1000);
}
```

### 3. 分层显示

可以根据价格范围分层显示标记,避免重叠:
```javascript
// 根据价格调整position
const priceLevel = Math.floor(signal.price / 100) % 3;
```

## 后续改进

1. **标记过滤**: 添加按类型/时间/盈亏过滤标记的功能
2. **标记统计**: 显示买入/卖出/平仓的次数统计
3. **标记导出**: 导出标记数据为CSV/JSON
4. **标记样式**: 自定义标记颜色、大小、形状
5. **标记交互**: 点击标记显示详细信息弹窗
6. **标记连线**: 连接开仓和平仓标记,显示完整交易

## 相关功能

- [CHART_FIX.md](CHART_FIX.md) - K线图表初始化修复
- [BUTTON_FIX.md](BUTTON_FIX.md) - 按钮状态修复
- [WEB_HOT_RELOAD.md](WEB_HOT_RELOAD.md) - Web服务热重载

## 技术栈

- **Lightweight Charts** v4.1.3 - 图表库
- **Flask-SocketIO** - WebSocket通信
- **WebSocket API** - 实时数据推送

## 总结

通过在回测过程中实时发送交易信号,并在前端使用Lightweight Charts的标记功能,我们成功实现了在K线图上显示买卖点的功能。这使得用户可以直观地看到:

1. ✅ 何时产生买入/卖出信号
2. ✅ 何时开仓/平仓
3. ✅ 每笔交易的盈亏情况
4. ✅ 交易信号的分布情况

这个功能对于策略分析和回测结果展示非常有帮助。
