# K线图标记从sim_log加载 - 完整实现

## 日期
2026-01-07

## 用户反馈

"图上买入点根据什么数据画的？不是sim_log吗？"

## 问题分析

### 原有实现的问题

**K线图标记的来源**:
- ❌ 只使用**实时WebSocket信号** (`trade_signal`事件)
- ❌ 只显示**开仓信号** (买入/卖出)
- ❌ 不显示**平仓、止盈、止损、回撤、超时**等事件
- ❌ 刷新页面后标记丢失

**sim_log表**:
- ✅ 包含**完整的交易日志** (开仓、平仓、止盈、止损等)
- ❌ **K线图没有使用这些数据!**

**结果**:
- K线图上的标记不完整
- 只显示开仓信号,看不到止盈止损
- 刷新页面后标记消失

---

## 解决方案

### 1. 新增API: /api/markers

**文件**: [web_app.py:494-593](web_app.py#L494-L593)

```python
@app.route('/api/markers', methods=['GET'])
def get_markers():
    """获取交易标记(从sim_log表读取,用于K线图显示)"""

    # 从sim_log表读取所有交易日志
    cursor.execute("""
        SELECT log_time, event, side, price, contracts, pnl
        FROM sim_log
        ORDER BY log_time ASC
        LIMIT 500
    """)

    # 根据事件类型设置标记样式
    if '开仓' in event:
        marker_type = 'buy' if side == 'long' else 'sell'
        color = '#26a69a' if side == 'long' else '#ef5350'  # 绿/红
        shape = 'arrowUp' if side == 'long' else 'arrowDown'

    elif 'TP' in event or '止盈' in event:
        marker_type = 'close'
        color = '#26a69a'  # 绿色表示止盈
        shape = 'circle'

    elif 'STOP' in event or '止损' in event:
        marker_type = 'close'
        color = '#ef5350'  # 红色表示止损
        shape = 'circle'

    elif 'CLOSE_RETREAT' in event or '回撤' in event:
        marker_type = 'close'
        color = '#ff9800'  # 橙色表示回撤
        shape = 'circle'

    elif 'EOD_CLOSE' in event or '超时' in event:
        marker_type = 'close'
        color = '#9e9e9e'  # 灰色表示超时
        shape = 'circle'
```

**返回格式**:
```json
{
  "success": true,
  "data": [
    {
      "time": 1704760240,
      "position": "belowBar",
      "color": "#26a69a",
      "shape": "arrowUp",
      "size": 2,
      "text": "开仓多头 @ 45061.80",
      "event": "开仓多头",
      "side": "long",
      "price": 45061.8,
      "pnl": 0.0
    },
    ...
  ]
}
```

---

### 2. 前端函数: loadMarkers()

**文件**: [web/templates/monitor.html:615-647](web/templates/monitor.html#L615-L647)

```javascript
function loadMarkers() {
    fetch('/api/markers')
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                console.log(`✓ 从sim_log加载${data.data.length}个交易标记`);

                // 清空现有标记
                tradeMarkers = [];

                // 添加新标记
                data.data.forEach(marker => {
                    tradeMarkers.push({
                        time: marker.time,
                        position: marker.position,
                        color: marker.color,
                        shape: marker.shape,
                        size: marker.size,
                        text: marker.text
                    });
                });

                // 应用到图表
                if (candleSeries) {
                    candleSeries.setMarkers(tradeMarkers);
                    console.log(`✓ 已应用${tradeMarkers.length}个交易标记到K线图`);
                }
            }
        });
}
```

---

### 3. 自动加载标记

**文件**: [web/templates/monitor.html:607-608](web/templates/monitor.html#L607-L608)

在K线加载完成后自动调用:

```javascript
// 更新图表成功后
console.log(`✓ 图表更新成功, ${candleData.length} 条数据, ${tradeMarkers.length} 个标记`);

// 自动加载交易标记
loadMarkers();
```

---

### 4. 手动刷新按钮

**文件**: [web/templates/monitor.html:117](web/templates/monitor.html#L117)

```html
<button type="button" class="btn btn-outline-success" onclick="loadMarkers()">刷新标记</button>
```

用户可以随时点击按钮重新加载标记。

---

## 标记样式设计

### 颜色和形状

| 事件类型 | 颜色 | 形状 | 位置 | 说明 |
|---------|------|------|------|------|
| **开仓多头** | 🟢 #26a69a | ↑ 箭头向上 | K线下方 | 绿色向上箭头 |
| **开仓空头** | 🔴 #ef5350 | ↓ 箭头向下 | K线上方 | 红色向下箭头 |
| **止盈 (TP)** | 🟢 #26a69a | ⚪ 圆圈 | K线上方 | 绿色圆圈 |
| **止损 (STOP)** | 🔴 #ef5350 | ⚪ 圆圈 | K线上方 | 红色圆圈 |
| **回撤 (RETREAT)** | 🟠 #ff9800 | ⚪ 圆圈 | K线上方 | 橙色圆圈 |
| **超时 (EOD)** | ⚫ #9e9e9e | ⚪ 圆圈 | K线上方 | 灰色圆圈 |

### 标记文字

```javascript
text: f"{event} @ {price:.2f}"
```

例如:
- `"开仓多头 @ 45061.80"`
- `"TP1.006 @ 45318.50"`
- `"STOP_LOSS @ 45200.00"`
- `"CLOSE_RETREAT @ 45000.00"`
- `"EOD_CLOSE @ 45100.00"`

---

## 使用流程

### 正常流程

1. **用户打开页面**
   - K线图初始化为空

2. **用户点击"启动"按钮**
   - 系统运行回测
   - 实时发送开仓信号 → WebSocket → 前端显示标记

3. **回测完成**
   - 自动调用 `loadMarkers()`
   - 从sim_log加载**所有**交易标记
   - 显示在K线图上

4. **用户点击"刷新标记"按钮**
   - 手动调用 `loadMarkers()`
   - 重新加载所有标记

### 数据来源对比

| 标记来源 | 触发时机 | 数据范围 | 持久性 |
|---------|---------|---------|--------|
| **WebSocket实时信号** (旧) | 回测过程中 | 仅开仓信号 | 刷新丢失 |
| **sim_log表** (新) | 加载K线后 | 所有交易事件 | 持久保存 |

---

## 效果对比

### 修复前

**K线图标记**:
```
↑ 开仓多头 @ 45061.80
↓ 开仓空头 @ 45500.00
```
- ❌ 只有开仓信号
- ❌ 看不到止盈止损
- ❌ 看不到完整的交易过程

### 修复后

**K线图标记**:
```
↑ 开仓多头 @ 45061.80 (绿色向上箭头)
⚪ TP1.006 @ 45318.50 (绿色圆圈)
⚪ TP1.012 @ 45575.20 (绿色圆圈)
⚪ TP1.018 @ 45831.90 (绿色圆圈)
⚪ TP1.024 @ 46088.60 (绿色圆圈)
⚪ TP1.03 @ 46345.30 (绿色圆圈)
```
或
```
↑ 开仓多头 @ 46432.40 (绿色向上箭头)
⚪ STOP_LOSS @ 45200.00 (红色圆圈)
```
- ✅ 显示所有交易事件
- ✅ 清晰看到止盈/止损位置
- ✅ 完整的交易历史

---

## 技术细节

### 1. 时间戳转换

sim_log表中的时间格式: `2024-01-08 13:10:00+00:00`

需要转换为Lightweight Charts所需的Unix时间戳(秒):

```python
from datetime import datetime

# 方法1: ISO格式
dt = datetime.fromisoformat(timestamp.replace('+00:00', ''))
time = int(dt.timestamp())

# 方法2: 字符串格式(备用)
dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
time = int(dt.timestamp())
```

### 2. 标记过滤

只显示在K线时间范围内的标记:

```javascript
// 检查标记是否在K线范围内
const inRange = marker.time >= klineTimeRange.min && marker.time <= klineTimeRange.max;

if (inRange) {
    validCount++;
} else {
    console.warn(`⚠️ 标记不在K线范围内: ${marker.time}`);
}
```

### 3. 标记数量限制

API限制返回500条:

```python
LIMIT 500
```

避免返回过多数据影响性能。

---

## 验证测试

### 测试步骤

1. **运行回测**
   ```bash
   python web_app.py
   # 浏览器访问 http://localhost:8076/monitor
   # 点击"启动"按钮运行回测
   ```

2. **检查sim_log数据**
   ```bash
   sqlite3 data/klines.db "SELECT event, side, price FROM sim_log ORDER BY log_time DESC LIMIT 10;"
   ```

3. **测试API**
   ```bash
   curl http://localhost:8076/api/markers | python3 -m json.tool | head -50
   ```

4. **检查前端显示**
   - 打开浏览器控制台
   - 查看 "✓ 从sim_log加载X个交易标记" 日志
   - 确认K线图上显示所有标记

### 预期结果

**控制台日志**:
```
✓ 从sim_log加载15个交易标记
✓ 已应用15个交易标记到K线图
✓ 图表更新成功, 14400 条数据, 15 个标记
```

**K线图显示**:
- 绿色向上箭头: 开仓多头
- 红色向下箭头: 开仓空头
- 绿色圆圈: 止盈 (TP1.006, TP1.012等)
- 红色圆圈: 止损
- 橙色圆圈: 回撤
- 灰色圆圈: 超时

---

## 优势

### 1. ✅ 完整的交易历史

- 显示所有交易事件,不仅仅是开仓
- 清晰看到止盈/止损位置
- 完整的交易链路

### 2. ✅ 数据持久化

- 数据存储在sim_log表
- 刷新页面不会丢失
- 可以查看历史交易

### 3. ✅ 与订单监控一致

- K线图标记 ↔ 订单监控表格
- 数据来源相同 (sim_log)
- 显示内容一致

### 4. ✅ 更好的可视化

- 不同颜色区分不同事件
- 形状区分开仓/平仓
- 清晰易读

---

## 相关文件

- **后端API**: [web_app.py:494-593](web_app.py#L494-L593) - /api/markers接口
- **前端函数**: [web/templates/monitor.html:615-647](web/templates/monitor.html#L615-L647) - loadMarkers()
- **自动加载**: [web/templates/monitor.html:607-608](web/templates/monitor.html#L607-L608) - 加载K线后自动调用
- **按钮**: [web/templates/monitor.html:117](web/templates/monitor.html#L117) - 刷新标记按钮

---

## 总结

通过从sim_log表加载K线图标记:

✅ **解决了数据来源问题** - 使用sim_log而不是实时信号
✅ **显示完整交易历史** - 开仓、止盈、止损、回撤、超时全部显示
✅ **数据持久化** - 刷新页面不会丢失标记
✅ **可视化增强** - 颜色和形状区分不同事件
✅ **与订单监控一致** - 数据源统一

现在K线图会显示完整的交易历史,一目了然! 🎉
