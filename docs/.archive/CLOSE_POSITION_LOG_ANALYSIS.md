# 平仓日志记录分析 - macd_refactor vs trade_engine

## 日期
2026-01-07

## 问题描述

分析macd_refactor.py在平仓时是否每层单独记录日志

---

## 核心发现

### ✅ macd_refactor.py 的日志记录策略

**止盈 (分级平仓)**:
- **每层都单独记录日志** ✅
- 只在最后一层才调用`close_position()`
- `close_position()`**不再记录日志**

**止损/回撤/超时 (全部平仓)**:
- 先记录日志 (STOP_LOSS / CLOSE_RETREAT / EOD_CLOSE)
- 再调用`close_position()`
- `close_position()`**不再记录日志**

### ❌ trade_engine.py 的问题

**止盈 (分级平仓)**:
- **每层都单独记录日志** ✅ (第445-456行)
- 最后一层调用`close_position()`
- `close_position()`**又记录了一次日志** ❌ (第324-334行)
- **导致重复记录!**

**止损/回撤/超时 (全部平仓)**:
- 先记录日志 ✅
- 再调用`close_position()`
- `close_position()`**又记录了一次日志** ❌
- **导致重复记录!**

---

## 详细分析

### 1. macd_refactor.py 的止盈日志

**代码位置**: [archive_old/macd_refactor.py:529-556](archive_old/macd_refactor.py#L529-L556)

```python
for info in levels:
    lvl = info['lvl']
    if lvl in pos.tp_hit:
        continue

    # 触发检查...
    if not triggered:
        continue

    # 计算利润...
    self.realized_pnl += net_btc
    pos.contracts -= sum_qty
    pos.tp_hit.append(lvl)

    # ✅ 第552行: 每层都记录日志
    self.record_log(
        ts,
        f"TP{info['lvl']}",           # 事件: TP1.006, TP1.012等
        pos.side,
        sale_price,
        sum_qty,                       # 平仓数量
        gross_pnl_btc,
        f"decay TP hit level {info['lvl']} close qty={sum_qty},回撤点{sale_price*(1-self.config.DRAWDOWN_POINTS)},剩余分数{pos.contracts}",
        0,
        0,
        self.realized_pnl
    )

    # ✅ 第553-555行: 只在全部平仓时才调用close_position
    if pos.contracts <= 0:
        self.close_position(pos, ts, sale_price, f"take_profit_decay_{info['lvl']}", net_btc)
        return True
```

**日志记录示例** (假设5层止盈,每层20张,总共100张):
```
1. TP1.006 - 平仓20张, 剩余80张
2. TP1.012 - 平仓20张, 剩余60张
3. TP1.018 - 平仓20张, 剩余40张
4. TP1.024 - 平仓20张, 剩余20张
5. TP1.03  - 平仓20张, 剩余0张 → 调用close_position (但不再记录日志)
```

**close_position方法** (第419-453行):
```python
def close_position(self, pos: Position, close_time, close_price, reason, net_btc: Optional[float] = None):
    # ... 计算利润 ...

    # 添加到trades列表
    self.trades.append(Trade(...))

    # 移除持仓
    self.positions.remove(pos)

    # ❌ 没有调用record_log()!
```

---

### 2. trade_engine.py 的止盈日志 (有重复记录问题)

**代码位置**: [trade_module/trade_engine.py:420-473](trade_module/trade_engine.py#L420-L473)

```python
for idx, lvl in enumerate(tp_levels):
    # ... 触发检查 ...

    # ✅ 第445-456行: 每层都记录日志
    self.record_log(
        ts,
        f"TP{lvl}",                # 事件: TP1.006, TP1.012等
        pos.side,
        sale_price,
        qty,                       # 平仓数量
        gross_pnl_btc,
        f"分级止盈触发 Lv{idx+1}/{len(tp_levels)} 平仓={qty}张 剩余={pos.contracts}张",
        0,
        0
    )

    # 更新合约数量
    pos.contracts -= qty
    pos.tp_hit.append(lvl)

    # ❌ 第467-472行: 最后一层调用close_position
    if pos.contracts <= 0:
        self.close_position(
            pos, ts, sale_price,
            f"take_profit_level_{idx+1}", net_btc
        )
        return True
```

**close_position方法** (第324-334行):
```python
# ❌ 第324-334行: 又记录了一次日志!
self.record_log(
    close_time,
    f"平仓({reason})",          # 事件: 平仓(take_profit_level_5)
    pos.side,
    close_price,
    pos.contracts,              # 剩余合约数 (此时为0)
    net_btc,
    f"平仓: {pos.entry_price:.2f} → {close_price:.2f}",
    close_fee_rate,
    abs(close_price * pos.contracts) * close_fee_rate
)
```

**日志记录示例** (假设5层止盈):
```
1. TP1.006 - 平仓20张, 剩余80张 ✅
2. TP1.012 - 平仓20张, 剩余60张 ✅
3. TP1.018 - 平仓20张, 剩余40张 ✅
4. TP1.024 - 平仓20张, 剩余20张 ✅
5. TP1.03  - 平仓20张, 剩余0张 ✅
   → close_position被调用
   → 平仓(take_profit_level_5) - 平仓0张 ❌ 重复记录!
```

---

### 3. 止损/回撤/超时日志对比

#### macd_refactor.py

**止损** (第589-590行):
```python
# ✅ 先记录日志
self.record_log(ts, 'STOP_LOSS', pos.side, hit_price, pos.contracts, gross_pnl_btc, ...)
# 再调用close_position (close_position不再记录日志)
self.close_position(pos, ts, sale_price, 'stop_loss', net_btc)
```

**回撤** (第680-681行):
```python
# ✅ 先记录日志
self.record_log(ts, "CLOSE_RETREAT", pos.side, sale_price, pos.contracts, gross_pnl_btc, ...)
# 再调用close_position (close_position不再记录日志)
self.close_position(pos, ts, sale_price, f"drawdown_close_±{dd}", gross_btc)
```

**超时** (第718-719行):
```python
# ✅ 先记录日志
self.record_log(ts, 'EOD_CLOSE', pos.side, price, pos.contracts, gross_pnl_btc, ...)
# 再调用close_position (close_position不再记录日志)
self.close_position(pos, ts, price, 'eod_close', gross_btc)
```

#### trade_engine.py

**止损** (第518-527行):
```python
# ✅ 先记录日志
self.record_log(ts, 'STOP_LOSS', pos.side, hit_price, pos.contracts, gross_pnl_btc, ...)
# ❌ 再调用close_position (close_position会再记录一次)
self.close_position(pos, ts, sale_price, 'stop_loss', net_btc)
```

**回撤** (第602-615行):
```python
# ✅ 先记录日志
self.record_log(ts, 'CLOSE_RETREAT', pos.side, sale_price, pos.contracts, gross_pnl_btc, ...)
# ❌ 再调用close_position (close_position会再记录一次)
self.close_position(pos, ts, sale_price, f'drawdown_close_{dd}', gross_btc)
```

**超时** (第703-707行):
```python
# ✅ 先记录日志
self.record_log(ts, 'EOD_CLOSE', pos.side, price, pos.contracts, gross_pnl_btc, ...)
# ❌ 再调用close_position (close_position会再记录一次)
self.close_position(pos, ts, price, 'eod_close', gross_btc)
```

---

## 重复记录的影响

### 问题1: 止盈最后一层重复记录

**示例**: 100张合约,5层止盈,每层20张

**macd_refactor日志** (5条):
```
TP1.006 | 20张 | 剩余80张
TP1.012 | 20张 | 剩余60张
TP1.018 | 20张 | 剩余40张
TP1.024 | 20张 | 剩余20张
TP1.03  | 20张 | 剩余0张
```

**trade_engine日志** (6条 - 有重复):
```
TP1.006 | 20张 | 剩余80张
TP1.012 | 20张 | 剩余60张
TP1.018 | 20张 | 剩余40张
TP1.024 | 20张 | 剩余20张
TP1.03  | 20张 | 剩余0张
平仓(take_profit_level_5) | 0张 | 剩余0张  ❌ 重复!
```

### 问题2: 止损/回撤/超时全部重复记录

**示例**: 止损100张

**macd_refactor日志** (1条):
```
STOP_LOSS | 100张
```

**trade_engine日志** (2条 - 有重复):
```
STOP_LOSS | 100张
平仓(stop_loss) | 0张  ❌ 重复!
```

---

## 解决方案

### 方案1: close_position不再记录日志 (推荐)

**修改**: [trade_module/trade_engine.py:324-334](trade_module/trade_engine.py#L324-L334)

```python
# ❌ 删除这段代码
# self.record_log(
#     close_time,
#     f"平仓({reason})",
#     pos.side,
#     close_price,
#     pos.contracts,
#     net_btc,
#     f"平仓: {pos.entry_price:.2f} → {close_price:.2f}",
#     close_fee_rate,
#     abs(close_price * pos.contracts) * close_fee_rate
# )
```

**优点**:
- 与macd_refactor完全一致
- 避免重复记录
- 日志更清晰

**缺点**:
- 如果有其他地方直接调用close_position,需要自己记录日志

---

### 方案2: 在调用close_position前添加标志 (备选)

在close_position方法中添加一个参数,控制是否记录日志:

```python
def close_position(self, pos: Position, close_time, close_price: float,
                   reason: str, net_btc: Optional[float] = None,
                   skip_log: bool = False):  # ✅ 新增参数
    """..."""

    # ... 计算利润 ...

    # 更新已实现盈亏
    self.realized_pnl += net_btc

    # 记录交易
    self.trades.append(trade)

    # ✅ 只在需要时记录日志
    if not skip_log:
        self.record_log(...)
```

调用时:
```python
# 止盈最后一层
self.close_position(pos, ts, sale_price, f"take_profit_level_{idx+1}", net_btc, skip_log=True)

# 止损
self.close_position(pos, ts, sale_price, 'stop_loss', net_btc, skip_log=True)
```

---

### 方案3: 保留现有行为,记录时检查pos.contracts

如果close_position必须记录日志,可以在记录前检查:

```python
# ✅ 只在有剩余合约时才记录
if pos.contracts > 0:
    self.record_log(
        close_time,
        f"平仓({reason})",
        pos.side,
        close_price,
        pos.contracts,
        net_btc,
        f"平仓: {pos.entry_price:.2f} → {close_price:.2f}",
        close_fee_rate,
        abs(close_price * pos.contracts) * close_fee_rate
    )
```

这样可以避免记录0张合约的日志。

---

## 建议采用方案1

### 理由

1. **完全符合macd_refactor的设计**
   - 日志记录在具体的业务逻辑中
   - close_position只负责清理工作

2. **避免歧义**
   - 止盈: 记录"TP1.006"等明确的事件
   - 止损: 记录"STOP_LOSS"
   - 回撤: 记录"CLOSE_RETREAT"
   - 超时: 记录"EOD_CLOSE"
   - 不需要一个额外的"平仓()"事件

3. **更清晰的责任分离**
   - 业务逻辑: 记录详细的事件日志
   - 清理方法: 只负责更新状态和清理数据

---

## 修改步骤

### 步骤1: 删除close_position中的日志记录

**文件**: `trade_module/trade_engine.py`
**位置**: 第324-334行

```python
# ❌ 删除这段代码
# # 记录日志
# self.record_log(
#     close_time,
#     f"平仓({reason})",
#     pos.side,
#     close_price,
#     pos.contracts,
#     net_btc,
#     f"平仓: {pos.entry_price:.2f} → {close_price:.2f}",
#     close_fee_rate,
#     abs(close_price * pos.contracts) * close_fee_rate
# )
```

### 步骤2: 验证所有调用位置

确认所有调用close_position的地方都已经记录了日志:

1. ✅ **止盈**: 第445-456行 - 已记录"TP{lvl}"
2. ✅ **止损**: 第518-525行 - 已记录"STOP_LOSS"
3. ✅ **回撤**: 第602-613行 - 已记录"CLOSE_RETREAT"
4. ✅ **超时**: 第703-707行 - 已记录"EOD_CLOSE"

### 步骤3: 测试验证

运行回测,检查日志:
- ✅ 止盈: 只看到"TP1.006", "TP1.012"等,没有重复的"平仓()"
- ✅ 止损: 只看到"STOP_LOSS",没有重复的"平仓(stop_loss)"
- ✅ 回撤: 只看到"CLOSE_RETREAT",没有重复的"平仓(drawdown_close)"
- ✅ 超时: 只看到"EOD_CLOSE",没有重复的"平仓(eod_close)"

---

## 总结

### 问题现状

- ❌ trade_engine.py存在**重复记录日志**的问题
- ❌ 每次平仓都会产生2条日志记录
- ❌ 止盈最后一层会记录1次"TP1.03" + 1次"平仓()"

### macd_refactor的设计

- ✅ close_position()**不记录日志**
- ✅ 每个业务逻辑自己记录详细的事件日志
- ✅ 避免重复记录

### 推荐修复

删除close_position()中的日志记录代码,与macd_refactor保持一致。

### 预期效果

修复后,trade_engine的日志将与macd_refactor完全一致,清晰易读!
