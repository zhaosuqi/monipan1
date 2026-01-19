# 信号描述修正 - 更清晰的统计信息

## 日期
2026-01-07

## 用户问题

"买入11这个数据从哪里来的？"

## 问题分析

### 原有描述的歧义

**后端日志**:
```
回测完成
总共处理: 12960 条K线
检测到信号: 多头11次 / 空头0次
```

**前端显示**:
```
回测完成 | 处理: 12960 | 买入: 11 | 卖出: 0
```

**问题**:
- ❌ "买入: 11" 容易误解为实际开仓了11次
- ❌ 不清楚这是信号数量还是实际交易数量
- ❌ 缺少实际开仓数量的信息

### 数据来源说明

**"买入: 11"** 的真实含义:
- 这是**检测到的多头开仓信号数量**
- 来源: `signal_calculator.calculate_open_signal()`
- 统计位置: [web_app.py:1372](web_app.py#L1372)
- **注意**: 这只是信号数量,不是实际开仓数量!

**代码**:
```python
# 统计信号
if signal and signal.action == 'open':
    if signal.side == 'long':
        buy_signals += 1  # 检测到多头信号,计数+1
    else:
        sell_signals += 1  # 检测到空头信号,计数+1
```

### 信号 vs 实际开仓的区别

| 项目 | 含义 | 可能的数值 | 说明 |
|------|------|-----------|------|
| **检测到信号** | signal_calculator计算得出的信号 | 11个 | 理论上的开仓机会 |
| **实际开仓** | trade_engine真正执行的开仓 | ≤11个 | 受资金、持仓限制等影响 |
| **完成交易** | 开仓+平仓的完整交易 | 需查询 | 从sim_log或trades统计 |

**示例**:
```
检测到信号: 11个
实际开仓: 8个 (3个因资金不足跳过)
完成交易: 8个 (全部平仓)
```

---

## 修正方案

### 1. 后端日志修正

**文件**: [web_app.py:1420-1421](web_app.py#L1420-L1421)

**修改前**:
```python
logger.info(f"检测到信号: 多头{buy_signals}次 / 空头{sell_signals}次")
```

**修改后**:
```python
logger.info(f"检测到信号: 多头{buy_signals}次 / 空头{sell_signals}次")
logger.info(f"实际开仓: {trade_engine.triggers_count}次")
```

**效果**:
```
回测完成
总共处理: 12960 条K线
检测到信号: 多头11次 / 空头0次
实际开仓: 8次
```

### 2. 前端进度显示修正

**文件**: [web/templates/monitor.html:359](web/templates/monitor.html#L359)

**修改前**:
```javascript
progressInfo.textContent = `已处理: ${data.processed}/${data.total} (${progressPercent}%) | 买入: ${data.buy_signals} | 卖出: ${data.sell_signals}`;
```

**修改后**:
```javascript
progressInfo.textContent = `已处理: ${data.processed}/${data.total} (${progressPercent}%) | 多头信号: ${data.buy_signals} | 空头信号: ${data.sell_signals}`;
```

**效果**:
```
已处理: 5000/12960 (38%) | 多头信号: 5 | 空头信号: 0
```

### 3. 前端完成提示修正

**文件**: [web/templates/monitor.html:383](web/templates/monitor.html#L383)

**修改前**:
```javascript
showToast(`回测完成！处理: ${data.processed}条 | 买入: ${data.buy_signals}次 | 卖出: ${data.sell_signals}次`, 'success');
```

**修改后**:
```javascript
showToast(`回测完成！处理: ${data.processed}条K线 | 多头信号: ${data.buy_signals}个 | 空头信号: ${data.sell_signals}个 | 实际开仓: ${data.total_trades}个`, 'success');
```

**效果**:
```
✅ 回测完成！处理: 12960条K线 | 多头信号: 11个 | 空头信号: 0个 | 实际开仓: 8个
```

### 4. 完成状态显示修正

**文件**: [web/templates/monitor.html:391](web/templates/monitor.html#L391)

**修改前**:
```javascript
progressInfo.textContent = `回测完成 | 处理: ${data.processed} | 买入: ${data.buy_signals} | 卖出: ${data.sell_signals}`;
```

**修改后**:
```javascript
progressInfo.textContent = `回测完成 | 处理: ${data.processed}条 | 多头信号: ${data.buy_signals} | 空头信号: ${data.sell_signals} | 实际开仓: ${data.total_trades}`;
```

**效果**:
```
回测完成 | 处理: 12960条 | 多头信号: 11 | 空头信号: 0 | 实际开仓: 8
```

---

## 修正效果对比

### 修正前 (容易误解)

**后端日志**:
```
回测完成
总共处理: 12960 条K线
检测到信号: 多头11次 / 空头0次
```

**前端显示**:
```
回测完成 | 处理: 12960 | 买入: 11 | 卖出: 0
```

**用户理解**:
- ❌ "买入11" → 以为开仓了11次
- ❌ 不知道实际开仓了多少次
- ❌ 不清楚信号和实际交易的关系

### 修正后 (清晰准确)

**后端日志**:
```
回测完成
总共处理: 12960 条K线
检测到信号: 多头11次 / 空头0次
实际开仓: 8次
```

**前端显示**:
```
回测完成 | 处理: 12960条 | 多头信号: 11 | 空头信号: 0 | 实际开仓: 8
```

**用户理解**:
- ✅ "多头信号: 11" → 明白是检测到的信号数量
- ✅ "实际开仓: 8" → 清楚知道真正开仓了8次
- ✅ 理解信号数量可能大于实际开仓(因资金限制等)

---

## 关键术语统一

### 修正前
- ❌ "买入" / "卖出" - 容易误解为实际交易
- ❌ "次" - 单位不够明确

### 修正后
- ✅ "多头信号" / "空头信号" - 明确表示是信号
- ✅ "实际开仓" - 明确表示真实交易
- ✅ "个" - 更自然的量词

---

## 数据统计说明

### 1. 信号数量统计

**统计位置**: [web_app.py:1370-1374](web_app.py#L1370-L1374)

```python
# 每次K线循环
signal = signal_calculator.calculate_open_signal(kline)

# 统计信号
if signal and signal.action == 'open':
    if signal.side == 'long':
        buy_signals += 1      # 多头开仓信号
    else:
        sell_signals += 1     # 空头开仓信号
```

**含义**:
- 策略识别出的开仓机会
- 不考虑资金、持仓限制等
- 理论上的最大交易次数

### 2. 实际开仓统计

**统计位置**: [trade_module/trade_engine.py](trade_module/trade_engine.py)

```python
def open_position(self, ...):
    # 检查资金、持仓限制等
    if available_capital <= 0:
        return False  # 资金不足,跳过开仓

    if insufficient or max_contracts <= 0:
        return False  # 合约数量不足,跳过开仓

    # 执行开仓
    self.triggers_count += 1  # 实际开仓计数+1
```

**含义**:
- 真正执行的开仓操作
- 考虑了资金、持仓限制等
- 实际发生的交易次数

### 3. total_trades统计

**统计位置**: [trade_module/trade_engine.py:763-808](trade_module/trade_engine.py#L763-L808)

```python
def get_statistics(self) -> Dict[str, Any]:
    total_trades = len(self.trades)  # 完成的交易数量
    ...
    return {
        'total_trades': total_trades,
        ...
    }
```

**含义**:
- 完整的交易(开仓+平仓)
- 从trades列表统计
- 不包括未平仓的持仓

---

## 典型场景示例

### 场景1: 正常情况

```
检测到信号: 多头11次
实际开仓: 11次
total_trades: 11次
```
✅ 信号充足,资金充足,全部开仓

### 场景2: 资金限制

```
检测到信号: 多头11次
实际开仓: 8次
total_trades: 7次
```
⚠️ 3个信号因资金不足跳过,1个持仓未平仓

### 场景3: 持仓限制

```
检测到信号: 多头11次
实际开仓: 6次
total_trades: 6次
```
⚠️ 策略限制同时持有多个仓位,5个信号被跳过

### 场景4: 止损冷却

```
检测到信号: 多头11次
实际开仓: 9次
total_trades: 9次
```
⚠️ 2个信号因止损冷却期被跳过

---

## 总结

### 修正内容

1. ✅ **后端日志** - 添加"实际开仓"统计
2. ✅ **前端进度显示** - "买入"改为"多头信号"
3. ✅ **完成提示** - 添加"实际开仓"数量
4. ✅ **术语统一** - 使用更明确的描述

### 改进效果

- ✅ **消除歧义** - 明确区分信号和实际交易
- ✅ **信息完整** - 同时显示信号数量和实际开仓
- ✅ **用户友好** - 描述更清晰易懂

### 现在的显示

```
回测完成 | 处理: 12960条 | 多头信号: 11 | 空头信号: 0 | 实际开仓: 8
```

**用户一目了然**:
- 检测到11个多头信号
- 实际开仓了8次
- 有3个信号因某种原因(资金、持仓限制等)未执行
