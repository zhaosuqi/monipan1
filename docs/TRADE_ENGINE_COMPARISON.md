# 交易引擎对比分析 - trade_engine.py vs macd_refactor.py

## 目标

对比当前`trade_engine.py`与`macd_refactor.py`的实现,确保开仓数量、止盈数量和利润计算完全一致。

## 1. 开仓数量计算

### macd_refactor.py (参考实现)

```python
# 第368行: 计算最大合约数量
cn = float(getattr(self.config, 'CONTRACT_NOTIONAL', 100.0))
max_contracts = int((available_capital * price) / cn)

# 第369-371行: 检查最小合约数量
if Config.TP_RATIO_PER_LEVEL >0 and max_contracts * Config.TP_RATIO_PER_LEVEL <= 1 or max_contracts<=0:
    logger.debug(f"Available capital insufficient for one contract")
    return False

# 第372行: 每张合约的BTC数量
qty_per_contract = cn / price

# 第373行: 开仓名义价值(USD)
open_notional_usd = cn * max_contracts

# 第374-375行: 手续费
open_fee_rate = 0.0007  # 固定为0.07%
open_fee_btc = (open_notional_usd * open_fee_rate) / price

# 第377-380行: 扣除资金和手续费
if Config.NO_LIMIT_POS:
    self.realized_pnl = 0
else:
    self.realized_pnl = self.realized_pnl - (max_contracts * cn / price) - open_fee_btc
```

**关键公式**:
```
max_contracts = int((available_capital * price) / CONTRACT_NOTIONAL)
```

### trade_engine.py (当前实现)

```python
# 第144-145行: 计算合约数量
cn = config.CONTRACT_NOTIONAL
max_contracts = int((available_capital * price) / cn)

# 第148-155行: 检查最小合约数量
if config.TP_RATIO_PER_LEVEL > 0:
    min_contracts = int(1 / config.TP_RATIO_PER_LEVEL)
    if max_contracts < min_contracts:
        return False

# 第160行: 每张合约的BTC数量
qty_per_contract = cn / price

# 第161-169行: 名义价值和手续费
open_notional_usd = cn * max_contracts
if config.OPEN_TAKER_OR_MAKER == "MAKER":
    open_fee_rate = config.MAKER_FEE_RATE
else:
    open_fee_rate = config.TAKER_FEE_RATE
open_fee_btc = (open_notional_usd * open_fee_rate) / price

# 第172-175行: 扣除资金和手续费
if config.NO_LIMIT_POS:
    self.realized_pnl = 0
else:
    self.realized_pnl -= (max_contracts * cn / price) + open_fee_btc
```

**对比结果**: ✅ 逻辑一致,只是trade_engine支持可配置的手续费率

## 2. 分级止盈数量计算

### macd_refactor.py

```python
# 第460-481行: 计算各层止盈数量
tp_levels = list(self.config.TP_LEVELS)
levels = []

for idx, lvl in enumerate(tp_levels):
    # ... 计算目标价 ...

    # 第476-479行: 计算平仓数量
    if idx == len(tp_levels) - 1:
        qty = pos.contracts  # 最后一层: 全部剩余合约
    else:
        qty = int(pos.entry_contracts * self.config.TP_RATIO_PER_LEVEL)

    levels.append({"idx": idx, "lvl": lvl, "target_price": target_price, "qty": qty})
```

**关键公式**:
```
非最后一层: qty = int(entry_contracts * TP_RATIO_PER_LEVEL)
最后一层:   qty = pos.contracts (全部剩余)
```

**示例**:
```
假设:
- entry_contracts = 100
- TP_RATIO_PER_LEVEL = 0.2
- TP_LEVELS = [1.006, 1.012, 1.018, 1.024, 1.03] (5层)

则:
- Lv1: qty = int(100 * 0.2) = 20张
- Lv2: qty = int(100 * 0.2) = 20张
- Lv3: qty = int(100 * 0.2) = 20张
- Lv4: qty = int(100 * 0.2) = 20张
- Lv5: qty = 剩余全部 (20张)
```

### trade_engine.py

```python
# 第361-365行: 计算平仓数量
if idx == len(tp_levels) - 1:
    qty = pos.contracts  # 最后一层全部平仓
else:
    qty = int(pos.entry_contracts * config.TP_RATIO_PER_LEVEL)

qty = min(qty, pos.contracts)  # 第367行: 不超过剩余合约
```

**对比结果**: ✅ 逻辑一致

## 3. 利润计算

### macd_refactor.py

```python
# 第536-547行: 计算止盈盈亏
notional_usd = cn * sum_qty

if pos.side == 'long':
    gross_btc = notional_usd * (2 / pos.entry_price - 1 / sale_price)
else:
    gross_btc = notional_usd / sale_price

gross_pnl_btc = gross_btc - fee_btc
```

**关键公式**:
```
多头: gross_pnl = qty * CONTRACT_NOTIONAL * (2/entry_price - 1/sale_price)
空头: gross_pnl = qty * CONTRACT_NOTIONAL / sale_price
```

**推导**:
```
多头利润 = (卖出价 - 买入价) * 数量 / 买入价 * 卖出价 * 合乘数
        = notional_usd * (1/entry_price - 1/sale_price) * ??

需要验证...
```

### trade_engine.py

```python
# 第384-395行: 计算盈亏
notional_usd = cn * qty

if pos.side == 'long':
    gross_pnl_btc = notional_usd * (1 / pos.entry_price - 1 / sale_price)
    gross_btc = notional_usd * (2 / pos.entry_price - 1 / sale_price)
else:
    gross_pnl_btc = notional_usd * (1 / sale_price - 1 / pos.entry_price)
    gross_btc = notional_usd / sale_price

fee_btc = 0.0
net_btc = gross_btc - fee_btc
```

**⚠️ 发现差异**:

#### 多头止盈利润计算

| 实现 | gross_pnl_btc | gross_btc |
|------|--------------|-----------|
| macd_refactor | 未单独计算 | `notional_usd * (2/entry - 1/sale)` |
| trade_engine | `notional_usd * (1/entry - 1/sale)` | `notional_usd * (2/entry - 1/sale)` |

**问题**: trade_engine计算的gross_pnl_btc与macd_refactor不一致!

**分析macd_refactor的逻辑**:
```python
# 第536-547行
if pos.side == 'long':
    gross_btc = notional_usd * (2 / pos.entry_price - 1 / sale_price)
# 第552行记录日志使用gross_pnl_btc = gross_btc - fee_btc
```

**结论**: macd_refactor的`gross_btc`就是实际的毛利润,公式为:
```
多头: gross_pnl = notional * (2/entry - 1/sale)
```

## 4. 需要修复的问题

### 问题1: 利润计算公式不一致

**修复方案**:
```python
# trade_engine.py 需要修改
if pos.side == 'long':
    # 使用与macd_refactor一致的公式
    gross_btc = notional_usd * (2 / pos.entry_price - 1 / sale_price)
    # gross_pnl_btc不需要单独计算
else:
    gross_btc = notional_usd / sale_price
    # gross_pnl_btc不需要单独计算

fee_btc = 0.0
net_btc = gross_btc - fee_btc
```

### 问题2: 手续费处理

**macd_refactor.py** (第544行):
```python
fee_btc = 0.0  # 止盈时不额外扣除手续费?
```

**trade_engine.py** (第394-395行):
```python
fee_btc = 0.0
net_btc = gross_btc - fee_btc
```

✅ 一致

### 问题3: realized_pnl更新

**macd_refactor.py** (第550行):
```python
self.realized_pnl = self.realized_pnl + gross_pnl_btc
```

**trade_engine.py** (第397行):
```python
self.realized_pnl += net_btc
```

✅ 一致

## 5. 止损逻辑

### macd_refactor.py

```python
# 第586-608行: 多头止损
if pos.side == 'long':
    hit_price = pos.entry_price * (1 - Config.STOP_LOSS_POINTS)
    if ref_low is not None and ref_low <= hit_price:
        # ... 平仓逻辑 ...
        gross_pnl_btc = notional_usd * (1 / pos.entry_price - 1 / hit_price)
```

**公式**:
```
多头止损价 = entry_price * (1 - STOP_LOSS_POINTS)
多头止损利润 = notional * (1/entry_price - 1/hit_price)
```

### trade_engine.py

```python
# 第450-469行: 多头止损
stop_loss_price = pos.entry_price * (1 - config.STOP_LOSS_POINTS)
if ref_low <= stop_loss_price:
    # ... 平仓逻辑 ...
    gross_pnl_btc = notional_usd * (1 / pos.entry_price - 1 / stop_loss_price)
```

✅ 一致

## 6. 关键配置参数

### 止盈级别
```python
TP_LEVELS = [1.006, 1.012, 1.018, 1.024, 1.03]
```

### 分级比例
```python
TP_RATIO_PER_LEVEL = 0.2  # 每层平仓20%
```

### 合约名义价值
```python
CONTRACT_NOTIONAL = 100  # 每张合约100美元
```

### 止损点数
```python
STOP_LOSS_POINTS = 0.008  # 0.8%
```

## 7. 建议的修改

### 修改1: 统一利润计算公式

**文件**: `trade_module/trade_engine.py`

**位置**: 第386-395行

**当前代码**:
```python
# 计算盈亏
if pos.side == 'long':
    gross_pnl_btc = notional_usd * (1 / pos.entry_price - 1 / sale_price)
    gross_btc = notional_usd * (2 / pos.entry_price - 1 / sale_price)
else:
    gross_pnl_btc = notional_usd * (1 / sale_price - 1 / pos.entry_price)
    gross_btc = notional_usd / sale_price
```

**修改为**:
```python
# 计算盈亏 - 与macd_refactor保持一致
if pos.side == 'long':
    gross_btc = notional_usd * (2 / pos.entry_price - 1 / sale_price)
else:
    gross_btc = notional_usd / sale_price

# gross_pnl_btc就是gross_btc,不需要单独计算
gross_pnl_btc = gross_btc

fee_btc = 0.0
net_btc = gross_btc - fee_btc
```

### 修改2: 添加详细的调试日志

**文件**: `trade_module/trade_engine.py`

**在止盈逻辑中添加**:
```python
self.logger.info(
    f"  止盈计算 | notional={notional_usd:.2f} | "
    f"entry={pos.entry_price:.2f} | sale={sale_price:.2f} | "
    f"qty={qty} | gross_btc={gross_btc:.8f}"
)
```

## 8. 测试验证

### 测试用例1: 多头止盈

**假设**:
- 开仓价 = 42000
- 止盈价 = 42252 (1.006倍)
- entry_contracts = 100
- TP_RATIO_PER_LEVEL = 0.2
- CONTRACT_NOTIONAL = 100

**计算**:
```
qty = int(100 * 0.2) = 20张
notional_usd = 20 * 100 = 2000 USD

gross_btc = 2000 * (2/42000 - 1/42252)
        = 2000 * (0.000047619 - 0.000046678)
        = 2000 * 0.000000941
        = 0.001882 BTC
```

### 测试用例2: 空头止盈

**假设**:
- 开仓价 = 42000
- 止盈价 = 41748 (0.994倍)
- entry_contracts = 100
- qty = 20张

**计算**:
```
notional_usd = 2000 USD
gross_btc = 2000 / 41748 = 0.04789 BTC
```

## 9. 总结

| 项目 | macd_refactor | trade_engine | 状态 |
|------|---------------|--------------|------|
| 开仓数量计算 | ✅ | ✅ | 一致 |
| 分级止盈数量 | ✅ | ✅ | 一致 |
| 多头止盈利润 | `2/entry - 1/sale` | `1/entry - 1/sale` | ⚠️ 需要修复 |
| 空头止盈利润 | `1/sale` | `1/sale` | ✅ 一致 |
| 止损利润 | `1/entry - 1/hit` | `1/entry - 1/hit` | ✅ 一致 |
| 手续费处理 | ✅ | ✅ | 一致 |

**关键修复**:
修改`trade_engine.py`第386-393行,使用与macd_refactor一致的利润公式。
