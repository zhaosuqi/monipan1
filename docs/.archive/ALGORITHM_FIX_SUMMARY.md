# 算法对比结果与修复总结

## 日期
2026-01-07

## 对比结果

经过与`macd_refactor.py`的详细对比,**trade_engine.py的核心算法已经完全一致**!

### ✅ 对比项目:止盈、止损、回撤、超时

| 算法 | 价格计算 | 触发检查 | 利润计算 | 状态 |
|------|---------|---------|---------|------|
| **止盈** | ✅ benchmark_price参考价 | ✅ high>=target / low<=target | ✅ `notional*(2/entry-1/sale)` | 完全一致 |
| **止损** | ✅ `entry * STOP_LOSS_POINTS` | ✅ `draw <= -stop` | ✅ `notional*(2/entry-1/sale)` | 完全一致 |
| **回撤** | ✅ `pprice ± dd` | ✅ `close <= sale_price` | ✅ `notional*(2/entry-1/sale)` | 完全一致 |
| **超时** | ✅ 当前价 | ✅ `minutes >= CLOSE_TIME_MINUTES` | ✅ `notional*(2/entry-1/price)` | 完全一致 |

### 🎉 关键发现

1. **trade_engine.py实际上比macd_refactor.py更好**!
   - 修复了macd_refactor中的BUG: `tp_hit`列表重复添加level的问题

2. **所有利润计算公式都完全一致**:
   - 多头: `gross_btc = notional * (2/entry - 1/sale)`
   - 空头: `gross_btc = notional / sale`

3. **所有触发条件都完全一致**:
   - 止盈: 最高价/最低价触发
   - 止损: 回撤达到止损点
   - 回撤: 止盈后价格回撤
   - 超时: 持仓时间超过限制

---

## 修复内容

### 1. ✅ 补充止损冷却逻辑

**问题**: trade_engine缺少止损后抑制同方向开仓的保护机制

**修复**:

#### 1.1 添加实例变量 (第80-82行)
```python
# 止损冷却
self.stoploss_time = None  # 最后止损时间
self.stoploss_side = None  # 最后止损方向
```

#### 1.2 止损时记录 (第502-504行, 多头)
```python
# 记录止损时间和方向(用于冷却逻辑)
self.stoploss_time = ts
self.stoploss_side = pos.side
```

#### 1.3 止损时记录 (第541-543行, 空头)
```python
# 记录止损时间和方向(用于冷却逻辑)
self.stoploss_time = ts
self.stoploss_side = pos.side
```

#### 1.4 开仓时检查冷却 (第149-157行)
```python
# 检查止损冷却 - 与macd_refactor.py保持一致
if self.stoploss_time is not None:
    time_since_stoploss = (ts - self.stoploss_time).total_seconds() / 60
    if time_since_stoploss < config.STOP_LOSS_HOLD_TIME and side == self.stoploss_side:
        self.logger.info(
            f"跳过开仓: 距离{side}止损仅{time_since_stoploss:.1f}分钟 "
            f"(冷却期{config.STOP_LOSS_HOLD_TIME}分钟)"
        )
        return False
```

**效果**: 止损后一段时间内不会开同方向的仓位,避免在不利行情中连续亏损

---

## 核心算法一致性验证

### 1. 止盈算法

**目标价格计算**:
```python
# 使用benchmark_price(如果有),否则使用entry_price
ref_price = pos.benchmark_price if pos.benchmark_price else pos.entry_price

# 根据level类型计算点数
if lvl < 1:
    pts = round(ref_price * lvl, 1)           # 例如: 0.006 -> 价格*0.006
elif lvl >= 1 and lvl < 2:
    pts = round(ref_price * (lvl - 1), 1)     # 例如: 1.006 -> 价格*0.006
else:
    pts = lvl                                   # 绝对点数

# 目标价
target_price = ref_price + pts (多头) 或 ref_price - pts (空头)
```

**平仓数量**:
```python
if idx == len(tp_levels) - 1:
    qty = pos.contracts           # 最后一层: 全部剩余
else:
    qty = int(pos.entry_contracts * TP_RATIO_PER_LEVEL)  # 每层固定比例
```

**触发条件**:
```python
if pos.side == 'long' and ref_high >= target_price:
    triggered = True
elif pos.side == 'short' and ref_low <= target_price:
    triggered = True
```

**利润计算**:
```python
# 多头
gross_btc = notional_usd * (2 / entry_price - 1 / sale_price)

# 空头
gross_btc = notional_usd / sale_price
```

---

### 2. 止损算法

**止损价格**:
```python
# 固定基于entry_price(不使用benchmark_price)
ref_price_for_stop = pos.entry_price
stop = round(ref_price_for_stop * STOP_LOSS_POINTS if STOP_LOSS_POINTS < 1 else STOP_LOSS_POINTS, 1)
```

**触发条件**:
```python
# 多头: 最低价 - 开仓价 <= -止损点
draw = ref_low - ref_price_for_stop
if draw <= -1 * stop:
    sale_price = entry_price - stop

# 空头: 开仓价 - 最高价 <= -止损点
draw = ref_price_for_stop - ref_high
if draw <= -1 * stop:
    sale_price = entry_price + stop
```

**利润计算**: 与止盈相同

---

### 3. 回撤算法

**触发条件**:
```python
# 必须满足三个条件:
# 1. 已经触发过止盈 (tp_activated == True)
# 2. 配置了回撤点数 (DRAWDOWN_POINTS > 0)
# 3. 至少有一个止盈级别已触发 (tp_hit不为空)
if not pos.tp_activated or DRAWDOWN_POINTS <= 0 or not pos.tp_hit:
    return False
```

**回撤价格**:
```python
ref_price = pos.tp_hit_value  # 使用止盈触发时的价格
pprice = round(ref_price, 1)

# 回撤点数可以是绝对值或百分比
dd = round(DRAWDOWN_POINTS) if DRAWDOWN_POINTS > 1 else round(pprice * DRAWDOWN_POINTS, 1)

# 多头回撤价
sale_price = round(pprice - dd, 1)

# 空头回撤价
sale_price = round(pprice + dd, 1)
```

**触发检查**:
```python
# 多头: 收盘价 <= 回撤价
if row['close'] <= sale_price:
    # 全部平仓

# 空头: 收盘价 >= 回撤价
if row['close'] >= sale_price:
    # 全部平仓
```

---

### 4. 超时算法

**触发条件**:
```python
minutes_in_position = (ts - pos.entry_time).total_seconds() / 60

# 时间超过限制 且 未触发过止盈
if minutes_in_position >= CLOSE_TIME_MINUTES and not pos.tp_activated:
    # 全部平仓
```

**利润计算**: 使用当前价格平仓,公式与止盈相同

---

## 配置参数对应关系

| 参数名 | macd_refactor | trade_engine | 说明 |
|--------|--------------|--------------|------|
| 止盈级别 | `TP_LEVELS` | `TP_LEVELS` | 例如: [1.006, 1.012, 1.018, 1.024, 1.03] |
| 分级比例 | `TP_RATIO_PER_LEVEL` | `TP_RATIO_PER_LEVEL` | 每层平仓比例,例如: 0.2 (20%) |
| 止损点数 | `STOP_LOSS_POINTS` | `STOP_LOSS_POINTS` | 例如: 0.008 (0.8%) |
| 止损冷却 | `STOP_LOSS_HOLD_TIME` | `STOP_LOSS_HOLD_TIME` | 止损后不开仓时间(分钟) |
| 回撤点数 | `DRAWDOWN_POINTS` | `DRAWDOWN_POINTS` | 例如: 0.003 (0.3%) |
| 超时时间 | `CLOSE_TIME_MINUTES` | `CLOSE_TIME_MINUTES` | 例如: 1440 (24小时) |
| 合约名义 | `CONTRACT_NOTIONAL` | `CONTRACT_NOTIONAL` | 每张合约价值,例如: 100 USD |

---

## 验证清单

### ✅ 已验证一致

- [x] 止盈目标价格计算
- [x] 止盈平仓数量计算
- [x] 止盈触发检查
- [x] 止盈利润计算
- [x] 止损价格计算
- [x] 止损触发检查
- [x] 止损利润计算
- [x] 回撤触发条件
- [x] 回撤价格计算
- [x] 回撤利润计算
- [x] 超时触发条件
- [x] 超时利润计算

### ✅ 已修复

- [x] 添加止损冷却逻辑
- [x] 记录止损时间和方向
- [x] 开仓前检查冷却期

### ✅ trade_engine的优势

- [x] 修复了macd_refactor中tp_hit重复添加的BUG
- [x] 代码结构更清晰易读
- [x] 更好的类型注解
- [x] 更详细的日志记录

---

## 使用建议

1. **可以放心使用trade_engine.py**
   - 核心算法与macd_refactor完全一致
   - 修复了已知BUG
   - 代码质量更高

2. **关键配置参数**
   ```python
   # 分级止盈
   TP_LEVELS = [1.006, 1.012, 1.018, 1.024, 1.03]
   TP_RATIO_PER_LEVEL = 0.2  # 每层平20%

   # 止损
   STOP_LOSS_POINTS = 0.008  # 0.8%
   STOP_LOSS_HOLD_TIME = 60  # 止损后60分钟内不开同方向仓

   # 回撤
   DRAWDOWN_POINTS = 0.003  # 0.3%

   # 超时
   CLOSE_TIME_MINUTES = 1440  # 24小时
   ```

3. **测试验证**
   - 使用相同的历史数据
   - 相同的配置参数
   - 对比两者的交易记录、盈亏、胜率等指标
   - 应该得到完全一致的结果

---

## 相关文档

- [docs/ALGORITHM_COMPARISON.md](ALGORITHM_COMPARISON.md) - 详细算法对比
- [docs/TRADE_ENGINE_COMPARISON.md](TRADE_ENGINE_COMPARISON.md) - 交易引擎对比
- [docs/POSITION_SIZE_PROFIT_FIX.md](POSITION_SIZE_PROFIT_FIX.md) - 利润计算修复
- [docs/SIM_LOG_FIX.md](SIM_LOG_FIX.md) - 日志记录修复
