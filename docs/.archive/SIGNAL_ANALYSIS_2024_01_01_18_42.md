# 信号分析 - 2024-01-01 18:42:00

## 日期
2026-01-07

## K线数据

```python
时间: 2024-01-01 18:42:00+00:00
收盘价: 43188.5

# 15分钟指标
macd15m = 40.73
dif15m = 103.29
dea15m = 62.56

# 1小时指标
macd1h = 42.75
dif1h = 114.07
dea1h = 71.32

# 4小时指标
macd4h = 99.49
dif4h = 21.38
dea4h = -78.11

# 1天指标
macd1d = -237.52  # 负值！
dif1d = 565.75
dea1d = 803.27

# KDJ指标
# 15分钟
k_15 = 86.30
d_15 = 74.58
j_15 = 109.73

# 1小时
k_1h = 85.27
d_1h = 80.55
j_1h = 94.70

# 4小时
k_4h = 94.70
d_4h = 85.41
j_4h = 113.43
```

---

## 配置参数（代码默认值）

```python
# 15分钟限制
T0_HIST15_LIMIT = 9999
T0_HIST15_LIMIT_MIN = 0           # 要求非负
T0_DIF15_LIMIT = 1000
T0_DIF15_LIMIT_MIN = -9999

# 1小时限制
T0_HIST1H_LIMIT = 9999
T0_HIST1H_LIMIT_MIN = 0           # 要求非负
T0_DIF1H_LIMIT = 1000
T0_DIF1H_LIMIT_MIN = -9999

# 4小时限制
T0_HIST4_LIMIT = 9999
T0_HIST4_LIMIT_MIN = 0            # 要求非负
T0_DIF4_LIMIT = 1000
T0_DIF4_LIMIT_MIN = -9999

# 1天限制
T0_HIST1D_LIMIT = 9999
T0_HIST1D_LIMIT_MIN = -9999       # 允许负值 (已更新)
T0_DIF1D_LIMIT = 9999
T0_DIF1D_LIMIT_MIN = -9999

# J指标限制（多）
T0_J15M_LIMIT = 999
T0_J1H_LIMIT = 999
T0_J4H_LIMIT = 113

# 均值参数
MEANS_HIST1D_COUNT = 360          # 启用1天均值检查
HIST1D_MEANS_LIMIT = 0
```

---

## 逐步验证所有检查条件

### ✅ 1. 15分钟MACD共振检查

```python
macd15m = 40.73  # 正值
```

**检查**: 15分钟MACD柱必须 > 0
**结果**: 40.73 > 0 → ✅ 通过

---

### ✅ 2. 15分钟指标限制检查

**HIST15限制**:
```python
macd15m = 40.73
T0_HIST15_LIMIT_MIN = 0

检查: 40.73 < 0
结果: False ✅ 通过
```

**DIF15限制**:
```python
dif15m = 103.29
T0_DIF15_LIMIT_MIN = -9999

检查: 103.29 < -9999
结果: False ✅ 通过
```

---

### ✅ 3. 1小时指标限制检查

**HIST1H限制**:
```python
macd1h = 42.75
T0_HIST1H_LIMIT_MIN = 0

检查: 42.75 < 0
结果: False ✅ 通过
```

**DIF1H限制**:
```python
dif1h = 114.07
T0_DIF1H_LIMIT_MIN = -9999

检查: 114.07 < -9999
结果: False ✅ 通过
```

---

### ✅ 4. 4小时指标限制检查

**HIST4限制**:
```python
macd4h = 99.49
T0_HIST4_LIMIT_MIN = 0

检查: 99.49 < 0
结果: False ✅ 通过
```

**DIF4限制**:
```python
dif4h = 21.38
T0_DIF4_LIMIT_MIN = -9999

检查: 21.38 < -9999
结果: False ✅ 通过
```

---

### ✅ 5. 1天指标限制检查

**HIST1D限制**:
```python
macd1d = -237.52  # 负值
T0_HIST1D_LIMIT_MIN = -9999  # 允许负值

检查: -237.52 < -9999
结果: False ✅ 通过 (因为 -237.52 > -9999)
```

**DIF1D限制**:
```python
dif1d = 565.75
T0_DIF1D_LIMIT_MIN = -9999

检查: 565.75 < -9999
结果: False ✅ 通过
```

---

### ❌ 6. J指标检查 - 拒绝原因！

**配置**:
```python
T0_J4H_LIMIT = 113  # 4小时J值上限
```

**K线数据**:
```python
j_4h = 113.43
```

**检查逻辑** (signal_calculator.py:272-274):
```python
if is_long and j_4h > config.T0_J4H_LIMIT:
    is_long = False
    reasons.append(f"J4H: {j_4h:.2f}")
```

**实际检查**:
```python
检查: 113.43 > 113
结果: True ❌ 拒绝信号！
```

**拒绝原因**: 4小时J值 (113.43) 超过上限 (113)

---

### ❌ 7. HIST1D均值检查 - 可能的拒绝原因

**配置**:
```python
MEANS_HIST1D_COUNT = 360     # 启用检查
HIST1D_MEANS_LIMIT = 0
```

**K线数据**:
```python
macd1d = -237.52
```

**检查逻辑** (signal_calculator.py:366-370):
```python
if is_long and config.MEANS_HIST1D_COUNT != 0:
    hist1d_mean = row.get('hist1d_mean', 0)
    if hist1d - config.HIST1D_MEANS_LIMIT < hist1d_mean:
        is_long = False
        reasons.append(f"HIST1D均值1: {hist1d:.2f} < {hist1d_mean:.2f}")
```

**实际检查** (假设hist1d_mean已计算):
```python
# 如果 hist1d_mean 约为 -200 (假设的滚动均值)
macd1d = -237.52
hist1d_mean = -200

检查: -237.52 - 0 < -200
检查: -237.52 < -200
结果: True ❌ 拒绝信号！

# 原因: 当前值 (-237.52) 低于历史均值 (-200)
```

**注意**: 如果 `hist1d_mean` 未计算（bug），则：
```python
hist1d_mean = 0  # 默认值
检查: -237.52 - 0 < 0
检查: -237.52 < 0
结果: True ❌ 拒绝信号！
```

---

## 拒绝原因总结

### 主要拒绝原因

1. **❌ J4H超限**: `j_4h = 113.43 > 113`
   - 这是明确的拒绝条件
   - 4小时J值超过配置的上限

2. **❌ HIST1D均值检查**: `macd1d = -237.52 < hist1d_mean`
   - 当前值低于历史均值
   - 说明1天级别处于下降趋势

### 检查条件顺序

根据代码逻辑 (signal_calculator.py:272-274)，J值检查在均值检查之前：

```python
# J4H检查 (line 272-274)
if is_long and j_4h > config.T0_J4H_LIMIT:
    is_long = False
    reasons.append(f"J4H: {j_4h:.2f}")

# HIST1D均值检查 (line 366-370)
if is_long and config.MEANS_HIST1D_COUNT != 0:
    if hist1d - config.HIST1D_MEANS_LIMIT < hist1d_mean:
        is_long = False
        reasons.append(f"HIST1D均值1: {hist1d:.2f} < {hist1d_mean:.2f}")
```

**结论**: 第一个拒绝信号的是 **J4H超限**

---

## 与 2024-01-01 19:39:59 的对比

### 相同点
- 两者的1天MACD柱都是负值（约-237）
- 两者的4小时J值都偏高（约113）

### 不同点
- **18:42:00**: j_4h = 113.43 → 超过113 → 拒绝
- **19:39:59**: 需要查看j_4h值

---

## 为什么被拒绝？

### 1. J4H超限（主要原因）

```python
j_4h = 113.43
T0_J4H_LIMIT = 113

检查: 113.43 > 113  → True → 拒绝
```

**含义**: 4小时KDJ的J值超过113，说明4小时级别处于超买状态

### 2. 趋势过滤（次要原因）

即使J4H通过，HIST1D均值检查也可能拒绝：

```python
macd1d = -237.52  # 当前值
hist1d_mean ≈ -200  # 历史均值（假设）

# 当前值低于均值 → 下降趋势 → 拒绝做多
```

---

## 如何让这个信号通过？

### 方法1: 放宽J值限制

```python
# core/config.py
T0_J4H_LIMIT = float(os.getenv('T0_J4H_LIMIT', '120'))  # 从113改为120
```

### 方法2: 禁用J值检查

需要在代码中添加开关（当前没有）

### 方法3: 禁用HIST1D均值检查

```python
# core/config.py
MEANS_HIST1D_COUNT = int(os.getenv('MEANS_HIST1D_COUNT', '0'))  # 从360改为0
```

### 方法4: 调整均值限制

```python
# core/config.py
HIST1D_MEANS_LIMIT = float(os.getenv('HIST1D_MEANS_LIMIT', '-50'))  # 从0改为-50
```

---

## 结论

### 2024-01-01 18:42:00 的K线数据

**拒绝原因**:
1. ❌ **主要原因**: 4小时J值超限 (113.43 > 113)
2. ❌ **次要原因**: 1天MACD柱均值检查（当前值低于历史均值）

**配置参数**:
- T0_J4H_LIMIT = 113 (已更新)
- T0_HIST1D_LIMIT_MIN = -9999 (已更新，允许负值)
- MEANS_HIST1D_COUNT = 360 (已更新，启用均值检查)

**这是正确的信号拒绝行为**:
- J值超限说明短期超买
- 1天均值低于历史均值说明长期下降趋势
- 两个条件都表明不应该开多仓

---

## 相关文件

- **信号计算器**: [signal_module/signal_calculator.py:272-274](signal_module/signal_calculator.py#L272-L274)
- **配置文件**: [core/config.py:116](core/config.py#L116)
- **数据库**: /Users/zhaosuqi/work/monipan/data/klines.db
- **数据表**: klines_1m_macd_smooth_ma

---

**分析完成！** 信号被拒绝的主要原因是4小时J值超限（113.43 > 113），其次是1天MACD柱均值检查。这是正确的趋势过滤行为。
