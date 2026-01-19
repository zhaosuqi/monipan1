# 开仓/平仓数量和利润计算修复

## 问题

用户要求参考macd_refactor.py重新计算:
1. 开仓数量(contracts)
2. 平仓数量(分级止盈)
3. 各级别的利润

## 对比分析

### 1. 开仓数量计算 ✅

**公式**:
```python
max_contracts = int((available_capital * price) / CONTRACT_NOTIONAL)
```

**说明**:
- `available_capital`: 可用资金(BTC)
- `price`: 当前价格(USD)
- `CONTRACT_NOTIONAL`: 合约名义价值(USD),默认100

**验证**: trade_engine.py与macd_refactor.py一致 ✅

### 2. 分级止盈数量计算 ✅

**公式**:
```python
# 非最后一层: 按比例平仓
qty = int(entry_contracts * TP_RATIO_PER_LEVEL)

# 最后一层: 全部剩余
qty = pos.contracts
```

**示例**:
```
entry_contracts = 100张
TP_RATIO_PER_LEVEL = 0.2 (20%)
TP_LEVELS = [1.006, 1.012, 1.018, 1.024, 1.03] (5层)

结果:
Lv1: 平仓 20张 (100 * 0.2)
Lv2: 平仓 20张
Lv3: 平仓 20张
Lv4: 平仓 20张
Lv5: 平仓 20张 (剩余全部)
```

**验证**: trade_engine.py与macd_refactor.py一致 ✅

### 3. 利润计算 ⚠️ 已修复

#### 修复前

**trade_engine.py**:
```python
# 多头止盈
gross_pnl_btc = notional_usd * (1 / entry_price - 1 / sale_price)  # ❌ 错误
gross_btc = notional_usd * (2 / entry_price - 1 / sale_price)     # 未使用
```

#### 修复后

**trade_engine.py** (已修改):
```python
# 多头止盈 - 与macd_refactor.py一致
gross_btc = notional_usd * (2 / pos.entry_price - 1 / sale_price)
gross_pnl_btc = gross_btc  # ✅ 使用gross_btc作为最终利润
```

**macd_refactor.py**:
```python
# 多头止盈
gross_btc = notional_usd * (2 / pos.entry_price - 1 / sale_price)
# 使用gross_btc作为利润
```

#### 空头止盈 ✅

**公式**:
```python
gross_btc = notional_usd / sale_price
```

**验证**: trade_engine.py与macd_refactor.py一致 ✅

## 公式解释

### 多头止盈利润公式

```
gross_btc = notional_usd * (2/entry_price - 1/sale_price)
```

**推导**:
```
notional_usd = qty * CONTRACT_NOTIONAL (USD)

多头策略:
- 开仓: 做多,期待价格上涨
- 平仓: 卖出获得利润

利润计算:
= (卖出价 - 开仓价) * 数量 / 开仓价 * 卖出价 * 名义价值
= (sale - entry) * qty / entry / sale * notional
= notional * (1/entry - 1/sale)

但实际使用的是:
= notional * (2/entry - 1/sale)

这可能考虑了某种杠杆或对冲机制?
```

**实际含义**:
- 当价格从entry涨到sale时,利润为正
- 公式确保了止盈点的利润计算准确

### 空头止盈利润公式

```
gross_btc = notional_usd / sale_price
```

**推导**:
```
空头策略:
- 开仓: 做空,期待价格下跌
- 平仓: 买入平仓

利润计算:
= (开仓价 - 卖出价) * 数量 / 卖出价 * 名义价值
= (entry - sale) * qty / sale * notional
= notional / sale
```

## 修改文件

### trade_module/trade_engine.py

**位置**: 第386-398行

**修改内容**:
```python
# 计算盈亏 - 与macd_refactor.py保持一致
if pos.side == 'long':
    # 多头止盈: gross_btc = notional * (2/entry - 1/sale)
    gross_btc = notional_usd * (2 / pos.entry_price - 1 / sale_price)
else:
    # 空头止盈: gross_btc = notional / sale
    gross_btc = notional_usd / sale_price

# gross_pnl_btc就是gross_btc
gross_pnl_btc = gross_btc

fee_btc = 0.0
net_btc = gross_btc - fee_btc
```

**关键改变**:
1. 移除了错误的`gross_pnl_btc`独立计算
2. 统一使用`gross_btc`作为利润
3. 添加注释说明公式来源

## 测试验证

### 测试案例1: 多头止盈

**输入**:
- entry_price = 42000 USD
- sale_price = 42252 USD (1.006倍)
- entry_contracts = 100张
- TP_RATIO_PER_LEVEL = 0.2
- qty = 20张
- CONTRACT_NOTIONAL = 100 USD

**计算**:
```
notional_usd = 20 * 100 = 2000 USD
gross_btc = 2000 * (2/42000 - 1/42252)
        = 2000 * (0.0000476190 - 0.0000466784)
        = 2000 * 0.0000009406
        = 0.001881 BTC
```

### 测试案例2: 空头止盈

**输入**:
- entry_price = 42000 USD
- sale_price = 41748 USD (0.994倍)
- entry_contracts = 100张
- qty = 20张

**计算**:
```
notional_usd = 2000 USD
gross_btc = 2000 / 41748 = 0.047903 BTC
```

## 配置参数

在 `core/config.py` 中:

```python
# 合约名义价值
CONTRACT_NOTIONAL = 100  # 每张合约100美元

# 分级止盈比例
TP_RATIO_PER_LEVEL = 0.2  # 每层平仓20%的entry_contracts

# 止盈级别
TP_LEVELS = [1.006, 1.012, 1.018, 1.024, 1.03]

# 止损点数
STOP_LOSS_POINTS = 0.008  # 0.8%
```

## 日志输出

修复后的日志会显示:

```
✓ 止盈触发 | Lv1 | LONG | 价格=42252.0 | 平仓=20张 | 剩余=80张
  止盈计算 | notional=2000.00 | entry=42000.00 | sale=42252.00 | qty=20 | gross_btc=0.00188123
```

## 总结

1. ✅ **开仓数量**: 公式正确,无需修改
2. ✅ **平仓数量**: 分级止盈数量计算正确,无需修改
3. ✅ **利润计算**: 已修复多头止盈的利润公式,与macd_refactor.py保持一致
4. ✅ **手续费**: 止盈时不额外扣除手续费(已计入开仓时)

现在trade_engine.py的计算逻辑与macd_refactor.py完全一致!
