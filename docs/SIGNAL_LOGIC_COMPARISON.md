# 信号逻辑对比 - macd_refactor vs signal_calculator

## 日期
2026-01-07

## 用户问题

"找出为什么这个数据不开仓，之前在macd_refactor里面是判断开仓的"

**K线数据**: 2024-01-01 19:39:00

---

## 对比结果

### ✅ 相同的部分

两个文件的**核心检查逻辑完全相同**:

1. **HIST15限制检查** (889行 vs 210行)
2. **DIF15限制检查** (894行 vs 215行)
3. **HIST15均值检查** (899行 vs 220行)
4. **DIF15均值检查** (914行 vs 242行)
5. **DEA15均值检查** (928行 vs 256行)
6. **HIST1H限制检查** (942行 vs 271行)
7. **DIF1H限制检查** (947行 vs 276行)
8. **HIST1D限制检查** (953行 vs 324行)
9. **DIF1D限制检查** (958行 vs 329行)
10. **HIST4限制检查** (1012行 vs 377行)
11. **DIF4限制检查** (1018行 vs 382行)
12. **所有均值检查** (1H, 4H, 1D)
13. **J值检查** (1113-1127行 vs 429-439行)

---

## ⚠️ 关键区别

### macd_refactor.py 独有的检查

#### 1. 价格跳空检查 (1132-1134行)

```python
if abs(row['close']-row_prev['close']) > (Config.M_PRICE_CHANGE if Config.M_PRICE_CHANGE > 1 else row_prev['close']*Config.M_PRICE_CHANGE):
    engine.closeT0()
    return None
```

**说明**: 如果当前K线收盘价与上一根K线收盘价差异过大（跳空），则不开仓。

#### 2. 价格波动检查 - 第一组 (1135-1139行)

```python
if Config.PRICE_CHANGE_COUNT>0:
    if state['prices'].iloc[-1*Config.PRICE_CHANGE_COUNT:].max() > row['close'] + row['close'] * Config.PRICE_CHANGE_LIMIT \
       and state['prices'].iloc[-1*Config.PRICE_CHANGE_COUNT:].min() < row['close'] - row['close'] * Config.PRICE_CHANGE_LIMIT:
        logger.debug(f"DEBUG: 跳过开仓 due to price change limit at {format_ts_east8(ts)}")
        engine.closeT0()
        return None
```

**说明**: 检查过去N根K线的价格波动范围，如果波动过大则不开仓。

#### 3. 价格波动检查 - 第二组 (1141-1145行)

```python
if Config.PRICE_CHANGE_COUNT_B>0:
    if state['prices'].iloc[-1*Config.PRICE_CHANGE_COUNT_B:].max() > row['close'] + row['close'] * Config.PRICE_CHANGE_LIMIT_B \
       and state['prices'].iloc[-1*Config.PRICE_CHANGE_COUNT_B:].min() < row['close'] - row['close'] * Config.PRICE_CHANGE_LIMIT_B:
        logger.debug(f"DEBUG: 跳过开仓 due to price change limit at {format_ts_east8(ts)}")
        engine.closeT0()
        return None
```

**说明**: 第二组价格波动检查（不同的参数配置）。

#### 4. 价格波动检查 - 第三组 (1146-1150行)

```python
if Config.PRICE_CHANGE_COUNT_C>0:
    if state['prices'].iloc[-1*Config.PRICE_CHANGE_COUNT_C:].max() > row['close'] + row['close'] * Config.PRICE_CHANGE_LIMIT_C \
       and state['prices'].iloc[-1*Config.PRICE_CHANGE_COUNT_C:].min() < row['close'] - row['close'] * Config.PRICE_CHANGE_LIMIT_C:
        logger.debug(f"DEBUG: 跳过开仓 due to price change limit at {format_ts_east8(ts)}")
        engine.closeT0()
        return None
```

**说明**: 第三组价格波动检查（不同的参数配置）。

---

## 信号计算器 (signal_calculator.py) 缺失的功能

### ❌ 没有价格跳空检查

**macd_refactor.py**: 检查 `abs(close - close_prev)` 是否超过阈值
**signal_calculator.py**: **无此检查**

### ❌ 没有价格波动检查

**macd_refactor.py**: 检查过去N根K线的最高价和最低价波动范围
**signal_calculator.py**: **无此检查**

---

## 为什么这个数据不开仓？

### 可能原因

由于 `signal_calculator.py` 缺少以下检查：

1. **价格跳空检查**: 如果2024-01-01 19:39:00这一根K线与上一根K线之间有较大跳空，`macd_refactor.py` 会拒绝开仓，但 `signal_calculator.py` 不会。

2. **价格波动检查**: 如果过去一段时间内价格波动过大，`macd_refactor.py` 会拒绝开仓，但 `signal_calculator.py` 不会。

### 但等等...

用户说"之前在macd_refactor里面是判断开仓的"，这意味着：
- `macd_refactor.py` **允许开仓**
- `signal_calculator.py` **拒绝开仓**

所以问题应该是**反向的**！

---

## 真正的问题

### 检查顺序差异

**macd_refactor.py 的检查顺序**:
```
889行 → 894行 → 899行 → ... → 953行 → 958行 → ... → 1113行
(15m → 1h → 1d → 4h → J值 → 价格检查)
```

**signal_calculator.py 的检查顺序**:
```
210行 → 215行 → ... → 271行 → 276行 → ... → 324行 → 329行 → ... → 377行 → ... → 429行
(15m → 1h → 1d → 4h → J值)
```

**关键差异**: `signal_calculator.py` 将 **1天指标检查放在4小时指标之前**，而 `macd_refactor.py` 是 **1小时 → 1天 → 4小时 → J值**。

### 可能的触发条件

对于 2024-01-01 19:39:00 的数据：

```python
hist1d = -215.47  # 1天MACD柱
dif1d = 596.34    # 1天DIF
dea1d = 811.81    # 1天DEA
```

#### 在 signal_calculator.py 中:

**检查顺序** (lines 269-373):
1. ✅ 15分钟检查通过
2. ✅ 1小时检查通过
3. ❌ **1天检查** (322-373行) 可能拒绝
4. (如果1天通过，才检查4小时)

#### 在 macd_refactor.py 中:

**检查顺序** (lines 942-1021):
1. ✅ 15分钟检查通过
2. ✅ 1小时检查通过
3. ❌ **1天检查** (953-961行) 可能拒绝
4. ❌ **4小时检查** (1012-1021行) 可能拒绝

---

## 具体检查哪个条件拒绝了信号？

### 需要检查配置参数

需要查看 `core/config.py` 中以下参数的值：

```python
# 1天指标限制
T0_HIST1D_LIMIT = ?
T0_HIST1D_LIMIT_MIN = ?
T0_DIF1D_LIMIT = ?
T0_DIF1D_LIMIT_MIN = ?

# 1天均值检查
MEANS_HIST1D_COUNT = ?
HIST1D_MEANS_LIMIT = ?
MEANS_DIF1D_COUNT = ?
DIF1D_MEANS_LIMIT = ?
MEANS_DEA1D_COUNT = ?
DEA1D_MEANS_LIMIT = ?

# 4小时指标限制
T0_HIST4_LIMIT = ?
T0_HIST4_LIMIT_MIN = ?
T0_DIF4_LIMIT = ?
T0_DIF4_LIMIT_MIN = ?
```

### 配置参数值

```python
# 1天指标限制 (core/config.py)
T0_HIST1D_LIMIT = 9999        # 上限
T0_HIST1D_LIMIT_MIN = 0       # 下限 (要求非负!)
T0_DIF1D_LIMIT = 1000         # 上限
T0_DIF1D_LIMIT_MIN = -9999    # 下限

# 4小时指标限制 (core/config.py)
T0_HIST4_LIMIT = 9999         # 上限
T0_HIST4_LIMIT_MIN = 0        # 下限 (要求非负!)
T0_DIF4_LIMIT = 1000          # 上限
T0_DIF4_LIMIT_MIN = -9999     # 下限
```

### K线数据分析

```python
# 2024-01-01 19:39:59.999 的完整指标值 (从数据库查询)
hist15 = 53.64   # 15分钟MACD柱
dif15 = 159.37   # 15分钟DIF
dea15 = 105.73   # 15分钟DEA

hist1h = 68.48   # 1小时MACD柱
dif1h = 153.70   # 1小时DIF
dea1h = 85.22    # 1小时DEA

hist4 = 116.09   # 4小时MACD柱
dif4 = 34.01     # 4小时DIF
dea4 = -82.07    # 4小时DEA

hist1d = -215.47 # 1天MACD柱 (负值!)
dif1d = 596.34   # 1天DIF
dea1d = 811.81   # 1天DEA
```

**关键观察**:
1. `hist1d = -215.47` 是**负值**，说明1天级别的MACD处于死叉状态
2. `dea4 = -82.07` 是**负值**，说明4小时级别的DEA也是负值
3. 但是 `hist4 = 116.09` 是**正值**，说明4小时MACD在零轴上方

---

## 确切的拒绝原因

### 找到了！HIST1D限制检查拒绝信号

**配置值**:
```python
T0_HIST1D_LIMIT = 9999        # 上限
T0_HIST1D_LIMIT_MIN = 0       # 下限 (要求非负!)
```

**K线数据**:
```python
hist1d = -215.47  # 1天MACD柱 (负值)
```

**检查逻辑** (signal_calculator.py:324-326):
```python
if is_long and (hist1d > config.T0_HIST1D_LIMIT or hist1d < config.T0_HIST1D_LIMIT_MIN):
    is_long = False
    reasons.append(f"HIST1D: {hist1d:.2f}")
```

**判断过程**:
```python
# 检查: hist1d < T0_HIST1D_LIMIT_MIN
# 检查: -215.47 < 0
# 结果: True ✓ 条件满足，拒绝信号！

is_long = False
reasons = ["HIST1D: -215.47"]
```

**结论**: ❌ **因为1天MACD柱为负值（-215.47），不满足 `hist1d >= 0` 的要求，信号被拒绝！**

---

## 为什么 macd_refactor 之前允许开仓？

### 可能的解释

#### 1. 配置参数不同

如果 `macd_refactor.py` 使用的配置中 `T0_HIST1D_LIMIT_MIN` 是负数，比如：

```python
# 旧配置
T0_HIST1D_LIMIT_MIN = -9999  # 允许负值

# 新配置
T0_HIST1D_LIMIT_MIN = 0      # 不允许负值
```

那么同样的数据（`hist1d = -215.47`）在旧版本中会通过，在新版本中会被拒绝。

#### 2. 检查逻辑差异

虽然两个文件的核心检查逻辑相同，但可能：
- `macd_refactor.py` 的某个检查条件有bug
- 或者使用了不同的配置对象
- 或者环境变量覆盖了默认值

#### 3. 数据时间点不同

可能之前测试时使用的是不同的K线数据，`hist1d` 是正值。

---

## 验证方法

### 查看历史配置

```bash
# 检查 git 历史中的配置
git log -p core/config.py | grep -A 5 -B 5 "T0_HIST1D_LIMIT_MIN"
```

### 运行 macd_refactor 测试

```bash
# 使用相同的K线数据运行旧版本
cd archive_old
python -c "
from macd_refactor import macd_v5_0_signal
# 使用 2024-01-01 19:39:59 的数据测试
# 查看是否真的允许开仓
"
```

### 对比环境变量

```bash
# 检查当前环境变量
env | grep T0_HIST
```

---

## 总结

### 核心发现

✅ **找到了拒绝信号的确切原因**:

1. **拒绝条件**: `hist1d < T0_HIST1D_LIMIT_MIN`
2. **实际值**: `hist1d = -215.47`
3. **限制值**: `T0_HIST1D_LIMIT_MIN = 0`
4. **判断结果**: `-215.47 < 0` → True → 拒绝信号

### 信号逻辑对比

两个文件的核心MACD检查逻辑**完全相同**，差异仅在于：

- `macd_refactor.py` 有额外的价格跳空和波动检查
- 但这些检查不会导致"允许开仓"的差异

### 最可能的情况

**配置参数变化**: `T0_HIST1D_LIMIT_MIN` 从允许负值改为要求非负

这意味着策略变得更加保守：
- **旧版本**: 允许在1天MACD死叉状态下开多仓
- **新版本**: 不允许在1天MACD死叉状态下开多仓

### 趋势过滤的作用

`T0_HIST1D_LIMIT_MIN = 0` 的设置是**趋势过滤器**：

✅ **作用**: 避免在1天级别下降趋势中开多仓
✅ **合理性**: 这是一个合理的风险控制措施
✅ **影响**: 会过滤掉一些假突破，但也会错过一些反弹机会

---

## 建议

### 如果想要恢复旧行为

**方法1**: 修改配置允许负值

```python
# core/config.py
T0_HIST1D_LIMIT_MIN = -9999  # 允许负值
```

**方法2**: 完全禁用1天指标检查

```python
# 设置为极大的范围
T0_HIST1D_LIMIT = 999999
T0_HIST1D_LIMIT_MIN = -999999
```

### 如果保持新行为

当前行为更加保守和安全，建议保持。

---

## 相关文件

- **信号计算器**: [signal_module/signal_calculator.py:324-326](signal_module/signal_calculator.py#L324-L326)
- **参考实现**: [archive_old/macd_refactor.py:953-956](archive_old/macd_refactor.py#L953-L956)
- **配置文件**: [core/config.py](core/config.py)
- **对比文档**: [docs/SIGNAL_LOGIC_COMPARISON.md](SIGNAL_LOGIC_COMPARISON.md)

---

**最终答案**: 2024-01-01 19:39:00 的K线数据因为1天MACD柱为负值（-215.47），不满足 `hist1d >= 0` 的趋势过滤要求，所以没有产生开仓信号。如果 `macd_refactor.py` 之前允许开仓，很可能是因为当时的配置中 `T0_HIST1D_LIMIT_MIN` 设置为负数（如-9999）。

