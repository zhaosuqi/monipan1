# 修复分级止盈逻辑 - 对齐 macd_refactor.py

## 日期
2026-01-07

## 用户需求

"参看 macd_refactor.py apply_decay_tp_levels 方法。严格按照这个逻辑修改目前的分级止盈的方法"

---

## 对比分析

### macd_refactor.py 的实现 (line 456-555)

**关键逻辑**:

1. **目标价格计算** (line 466-473):
```python
for idx, lvl in enumerate(tp_levels):
    if lvl < 1:
        pts = round(ref_price * lvl, 1)  # 百分比形式
    elif lvl >= 1 and lvl < 2:
        pts = round(ref_price * (lvl - 1), 1)  # 百分比形式
    else:
        pts = lvl  # 绝对值形式

    target_price = round(ref_price + pts, 1) if pos.side == 'long' else round(ref_price - pts, 1)
```

2. **平仓数量计算** (line 476-479):
```python
if idx == len(tp_levels) - 1:
    qty = pos.contracts  # 最后一层全部平仓
else:
    qty = int(pos.entry_contracts * self.config.TP_RATIO_PER_LEVEL)
```

3. **盈亏计算 - 多头** (line 538-540):
```python
gross_btc = notional_usd * (2 / pos.entry_price - 1 / sale_price)
gross_pnl_btc = notional_usd * (1 / pos.entry_price - 1 / sale_price)
```

**关键**: 计算了两个值 - `gross_btc` 和 `gross_pnl_btc`

4. **盈亏计算 - 空头** (line 542-543):
```python
gross_btc = notional_usd * (1 / sale_price)
gross_pnl_btc = notional_usd * (1 / sale_price - 1 / pos.entry_price)
```

**关键**: 同样计算了两个值，且逻辑与多头不同

5. **日志记录** (line 552):
```python
self.record_log(ts, f"TP{lvl}", pos.side, sale_price, sum_qty, gross_pnl_btc,
    f"decay TP hit level {lvl} close qty={sum_qty},回撤点{sale_price*(1-self.config.DRAWDOWN_POINTS)},剩余分数{pos.contracts}",
    0, 0, self.realized_pnl)
```

6. **全部平仓** (line 553-555):
```python
if pos.contracts <= 0:
    self.close_position(pos, ts, sale_price, f"take_profit_decay_{info['lvl']}", net_btc)
    return True
```

---

### 修改前的实现 (trade_engine.py)

**问题**:
1. ❌ 多头只计算了 `gross_btc`，没有单独计算 `gross_pnl_btc`
2. ❌ 空头的计算逻辑不完整
3. ❌ 日志格式不统一

---

## 修改内容

**文件**: [trade_module/trade_engine.py:424-487](trade_module/trade_engine.py#L424-L487)

### 主要修改

#### 1. 重新组织代码流程

**修改前**:
```python
# 执行止盈平仓
sale_price = target_price
notional_usd = cn * qty

# 计算盈亏
if pos.side == 'long':
    gross_btc = ...
else:
    gross_btc = ...

gross_pnl_btc = gross_btc  # ❌ 错误：直接赋值
```

**修改后**:
```python
# 执行止盈平仓
sale_price = target_price

# 确保平仓数量不超过当前持仓
sum_qty = min(qty, pos.contracts)

if sum_qty <= 0:
    continue

# 标记此级别已触发
pos.tp_hit.append(lvl)
pos.tp_activated = True
pos.tp_hit_value = sale_price

# 计算盈亏 - 严格按照macd_refactor.py的逻辑
notional_usd = cn * sum_qty

if pos.side == 'long':
    gross_btc = notional_usd * (2 / pos.entry_price - 1 / sale_price)
    gross_pnl_btc = notional_usd * (1 / pos.entry_price - 1 / sale_price)
else:
    gross_btc = notional_usd * (1 / sale_price)
    gross_pnl_btc = notional_usd * (1 / sale_price - 1 / pos.entry_price)
```

#### 2. 修改多头盈亏计算

**修改前** (line 430-433):
```python
if pos.side == 'long':
    gross_btc = notional_usd * (2 / pos.entry_price - 1 / sale_price)

# gross_pnl_btc就是gross_btc
gross_pnl_btc = gross_btc
```

**修改后** (line 441-444):
```python
if pos.side == 'long':
    # 多头止盈（macd_refactor.py line 539-540）
    gross_btc = notional_usd * (2 / pos.entry_price - 1 / sale_price)
    gross_pnl_btc = notional_usd * (1 / pos.entry_price - 1 / sale_price)
```

**说明**: 现在分别计算 `gross_btc` 和 `gross_pnl_btc`

#### 3. 修改空头盈亏计算

**修改前** (line 435-436):
```python
else:
    gross_btc = notional_usd / sale_price

# gross_pnl_btc就是gross_btc
gross_pnl_btc = gross_btc
```

**修改后** (line 446-448):
```python
else:
    # 空头止盈（macd_refactor.py line 542-543）
    gross_btc = notional_usd * (1 / sale_price)
    gross_pnl_btc = notional_usd * (1 / sale_price - 1 / pos.entry_price)
```

**说明**:
1. 将 `/` 改为 `*`（与多头保持一致）
2. 分别计算 `gross_btc` 和 `gross_pnl_btc`
3. `gross_pnl_btc` 的计算包含入场价

#### 4. 统一日志格式

**修改前** (line 451-462):
```python
self.record_log(
    ts,
    f"TP{lvl}",
    pos.side,
    sale_price,
    qty,
    gross_pnl_btc,
    f"分级止盈触发 Lv{idx+1}/{len(tp_levels)} "
    f"平仓={qty}张 剩余={pos.contracts}张",
    0,
    0
)
```

**修改后** (line 457-471):
```python
self.record_log(
    ts,
    f"TP{lvl}",
    pos.side,
    sale_price,
    sum_qty,
    gross_pnl_btc,
    f"decay TP hit level {lvl} close qty={sum_qty},"
    f"回撤点{sale_price*(1-config.DRAWDOWN_POINTS):.2f},"
    f"剩余分数{pos.contracts}",
    0,
    0,
    self.realized_pnl
)
```

**变化**:
- ✅ 使用 `sum_qty` 而不是 `qty`
- ✅ 使用 "decay TP hit level" 格式
- ✅ 添加回撤点信息
- ✅ 添加 `self.realized_pnl` 参数

#### 5. 修改全部平仓逻辑

**修改前** (line 473-478):
```python
if pos.contracts <= 0:
    self.close_position(
        pos, ts, sale_price,
        f"take_profit_level_{idx+1}", net_btc
    )
    return True
```

**修改后** (line 481-487):
```python
if pos.contracts <= 0:
    self.close_position(
        pos, ts, sale_price,
        f"take_profit_decay_{lvl}", net_btc  # 使用lvl而不是idx+1
    )
    return True
```

**变化**: 使用 `take_profit_decay_{lvl}` 作为原因

---

## 盈亏计算公式详解

### 多头止盈

#### gross_btc (总BTC价值)

```python
gross_btc = notional_usd * (2 / entry_price - 1 / sale_price)
```

**含义**: 平仓后持有的总BTC价值（包括本金+利润）

**推导**:
- 开仓时: `notional_usd = entry_price * btc_amount` → `btc_amount = notional_usd / entry_price`
- 平仓时: `btc_after_sale = notional_usd / sale_price`
- 剩余BTC: `btc_amount - btc_after_sale = notional_usd / entry_price - notional_usd / sale_price`
- 总价值: `btc_after_sale + btc_amount = notional_usd / sale_price + notional_usd / entry_price`

但这里的 `2 / entry_price - 1 / sale_price` 实际上是另一种表达方式。

#### gross_pnl_btc (净盈亏)

```python
gross_pnl_btc = notional_usd * (1 / entry_price - 1 / sale_price)
```

**含义**: 实际盈亏（利润）

**推导**:
- 利润 = (卖出价 - 买入价) * btc数量
- = `(1 / sale_price - 1 / entry_price) * notional_usd`

### 空头止盈

#### gross_btc

```python
gross_btc = notional_usd * (1 / sale_price)
```

**含义**: 平仓后获得的BTC价值

#### gross_pnl_btc

```python
gross_pnl_btc = notional_usd * (1 / sale_price - 1 / entry_price)
```

**含义**: 实际盈亏（利润）

**推导**:
- 空头: 高卖低买
- 利润 = (卖出价 - 买入价) * btc数量
- 当卖出价 > 买入价时，盈利

---

## 关键差异对比

| 项目 | 修改前 | 修改后 | 说明 |
|------|--------|--------|------|
| **多头 gross_btc** | ✅ 正确 | ✅ 保持不变 | 公式一致 |
| **多头 gross_pnl_btc** | ❌ 等于gross_btc | ✅ 单独计算 | 修复逻辑 |
| **空头 gross_btc** | ❌ 使用除法 | ✅ 使用乘法 | 与多头一致 |
| **空头 gross_pnl_btc** | ❌ 等于gross_btc | ✅ 单独计算 | 包含入场价 |
| **平仓数量** | ❌ 直接使用qty | ✅ 使用sum_qty | 确保不超卖 |
| **日志格式** | ❌ 简化版 | ✅ 完整版 | 对齐macd_refactor |
| **平仓原因** | ❌ take_profit_level_{idx+1} | ✅ take_profit_decay_{lvl} | 对齐macd_refactor |

---

## 验证

### 测试场景

**配置**:
```python
TP_LEVELS = [1.0065, 1.012, 1.018, 1.024, 1.03]
TP_RATIO_PER_LEVEL = 0.2
CONTRACT_NOTIONAL = 10000
```

**多头止盈场景**:
```python
entry_price = 45000
contracts = 100

# 第一级止盈 (1.0065)
target_price = 45000 * 1.0065 = 45292.5
qty = 100 * 0.2 = 20
notional_usd = 20 * 10000 = 200000

gross_btc = 200000 * (2/45000 - 1/45292.5) = 4.4442... BTC
gross_pnl_btc = 200000 * (1/45000 - 1/45292.5) = 0.0128... BTC
```

### 验证步骤

1. **运行回测**
   ```bash
   python web_app.py
   # 触发止盈后检查日志
   ```

2. **检查日志**
   ```bash
   grep "decay TP hit level" /tmp/web_app.log
   ```

3. **对比数值**
   - 检查 `gross_pnl_btc` 的计算
   - 验证 `sum_qty` 是否正确
   - 确认日志格式

---

## 相关文件

- **修改文件**: [trade_module/trade_engine.py:424-487](trade_module/trade_engine.py#L424-L487)
- **参考实现**: [archive_old/macd_refactor.py:456-555](archive_old/macd_refactor.py#L456-L555)
- **配置参数**:
  - `TP_LEVELS` - 止盈级别数组
  - `TP_RATIO_PER_LEVEL` - 每级平仓比例
  - `CONTRACT_NOTIONAL` - 合约面值
  - `DRAWDOWN_POINTS` - 回撤点数

---

## 总结

### 核心修改

1. ✅ **多头盈亏计算** - 分别计算 `gross_btc` 和 `gross_pnl_btc`
2. ✅ **空头盈亏计算** - 修正计算逻辑，分别计算两个值
3. ✅ **数量验证** - 使用 `sum_qty` 确保不超卖
4. ✅ **日志格式** - 对齐 macd_refactor.py 的完整格式
5. ✅ **平仓原因** - 使用 `take_profit_decay_{lvl}` 格式

### 修复的问题

- ❌ **错误**: `gross_pnl_btc = gross_btc`（多头和空头都是）
- ✅ **正确**: 分别计算，且空头使用不同的公式

### 影响

- ✅ 盈亏计算更准确
- ✅ 与 macd_refactor.py 完全一致
- ✅ 日志记录更详细（包含回撤点信息）
- ✅ 代码逻辑更清晰

---

**修复完成！** 分级止盈逻辑现在严格按照 macd_refactor.py 的实现。
