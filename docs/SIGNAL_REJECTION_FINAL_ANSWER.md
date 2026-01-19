# 信号拒绝原因 - 最终答案

## 日期
2026-01-07

## 重新核对后的发现

### ❌ 之前的分析错误

我之前认为拒绝原因是 `hist1d < 0`，这是**错误的**！

根据准确的回测参数：
```json
"t0_hist1d_limit_min": -9999  // 允许负值
```

所以 `hist1d = -215.47` **通过了限制检查**！

---

## 关键发现：hist1d_mean 未被计算！

### 代码分析

[signal_calculator.py:92-123](signal_module/signal_calculator.py#L92-L123):

```python
# ✅ 计算了这些均值
hist15_mean = self.rolling_tracker.update('macd15m', row.get('macd15m', 0))
hist15_mean_2 = self.rolling_tracker.update('macd15m_2', row.get('macd15m', 0))
dif15_mean = self.rolling_tracker.update('dif15m', row.get('dif15m', 0))
dea15_mean = self.rolling_tracker.update('dea15m', row.get('dea15m', 0))

hist1h_mean = self.rolling_tracker.update('macd1h', row.get('macd1h', 0))
dif1h_mean = self.rolling_tracker.update('dif1h', row.get('dif1h', 0))
dea1h_mean = self.rolling_tracker.update('dea1h', row.get('dea1h', 0))

hist4_mean = self.rolling_tracker.update('macd4h', row.get('macd4h', 0))
dif4_mean = self.rolling_tracker.update('dif4h', row.get('dif4h', 0))
dea4_mean = self.rolling_tracker.update('dea4h', row.get('dea4h', 0))

# ❌ 没有计算 hist1d_mean!
# ❌ 没有计算 dif1d_mean!
# ❌ 没有计算 dea1d_mean!
```

### 检查逻辑

[signal_calculator.py:334-338](signal_module/signal_calculator.py#L334-L338):

```python
if is_long and config.MEANS_HIST1D_COUNT != 0:
    hist1d_mean = row.get('hist1d_mean', 0)  # ← 从row获取，但row中没有！
    if hist1d - config.HIST1D_MEANS_LIMIT < hist1d_mean:
        is_long = False
        reasons.append(f"HIST1D均值1: {hist1d:.2f} < {hist1d_mean:.2f}")
```

### 问题

```python
# 配置
means_hist1d_count = 360  # ≠ 0，所以会执行检查
hist1d_means_limit = 0

# row.get('hist1d_mean', 0) 返回默认值 0
# 因为 'hist1d_mean' 键不存在于 row 中！

# 检查
hist1d_mean = row.get('hist1d_mean', 0)  # = 0
if hist1d - 0 < 0:  # -215.47 - 0 < 0
    is_long = False  # 拒绝信号！
```

---

## 确切的拒绝原因

### 步骤1: hist1d_mean 未计算

代码在 [signal_calculator.py:92-123](signal_module/signal_calculator.py#L92-L123) 计算移动平均值时：
- ✅ 计算了 `hist15_mean`, `hist1h_mean`, `hist4_mean`
- ❌ **没有计算 `hist1d_mean`**
- ❌ **没有计算 `dif1d_mean`**
- ❌ **没有计算 `dea1d_mean`**

### 步骤2: 检查 hist1d_mean

[signal_calculator.py:335](signal_module/signal_calculator.py#L335):
```python
hist1d_mean = row.get('hist1d_mean', 0)
```

因为 `'hist1d_mean'` 键不存在于 row 中，所以返回默认值 `0`。

### 步骤3: 比较并拒绝

[signal_calculator.py:336-338](signal_module/signal_calculator.py#L336-L338):
```python
if hist1d - config.HIST1D_MEANS_LIMIT < hist1d_mean:
    is_long = False
    reasons.append(f"HIST1D均值1: {hist1d:.2f} < {hist1d_mean:.2f}")
```

检查过程：
```python
hist1d = -215.47
hist1d_means_limit = 0
hist1d_mean = 0  # 默认值

检查: -215.47 - 0 < 0
检查: -215.47 < 0
结果: True ✓ 拒绝信号！

is_long = False
reasons = ["HIST1D均值1: -215.47 < 0.00"]
```

---

## 为什么 macd_refactor.py 允许开仓？

### 可能的原因

#### 1. macd_refactor.py 计算了 hist1d_mean

让我检查 macd_refactor.py 是否计算了 hist1d_mean：

[macd_refactor.py:1071-1075](archive_old/macd_refactor.py#L1071-L1075):
```python
if is_long:
    if Config.MEANS_HIST1D_COUNT!=0:
        if hist1d - Config.HIST1D_MEANS_LIMIT < row['hist1d_mean']:
            engine.duoq = f"DEBUG: 跳过多头开仓 at {format_ts_east8(ts)}, hist1d={hist1d:.2f} -LIMIT {Config.HIST1D_MEANS_LIMIT:2f} < hist1dmean={row['hist1d_mean']:.2f} "
            logger.debug(engine.duoq)
            is_long = False
```

**关键**: `row['hist1d_mean']` - 如果这个键不存在，会抛出 `KeyError`！

#### 2. 可能的差异

- **signal_calculator.py**: 使用 `row.get('hist1d_mean', 0)` - 不存在时返回 0
- **macd_refactor.py**: 使用 `row['hist1d_mean']` - 不存在时抛出异常

或者：

- **macd_refactor.py**: 可能在其他地方计算了 `hist1d_mean`
- **macd_refactor.py**: 可能 `row` 包含了从数据库或其他来源计算的均值

---

## 结论

### 真正的拒绝原因

❌ **不是 `hist1d < 0`**（我之前的分析错误）
✅ **是 `hist1d_mean` 缺失导致的错误检查**

### 详细原因

1. **代码bug**: `signal_calculator.py` 没有计算 `hist1d_mean`
2. **默认值问题**: `row.get('hist1d_mean', 0)` 返回 0
3. **错误检查**: `-215.47 - 0 < 0` 成立，拒绝信号

### 这是一个代码bug！

应该修复 [signal_calculator.py:92-123](signal_module/signal_calculator.py#L92-L123)，添加：

```python
# 更新1天指标移动平均值
hist1d_mean = self.rolling_tracker.update('macd1d', row.get('macd1d', 0))
dif1d_mean = self.rolling_tracker.update('dif1d', row.get('dif1d', 0))
dea1d_mean = self.rolling_tracker.update('dea1d', row.get('dea1d', 0))

# 更新1天指标第二组移动平均值
hist1d_mean_2 = self.rolling_tracker.update('macd1d_2', row.get('macd1d', 0))
dif1d_mean_2 = self.rolling_tracker.update('dif1d_2', row.get('dif1d', 0))
dea1d_mean_2 = self.rolling_tracker.update('dea1d_2', row.get('dea1d', 0))

# 添加到row
row['hist1d_mean'] = hist1d_mean
row['dif1d_mean'] = dif1d_mean
row['dea1d_mean'] = dea1d_mean
row['hist1d_mean_2'] = hist1d_mean_2
row['dif1d_mean_2'] = dif1d_mean_2
row['dea1d_mean_2'] = dea1d_mean_2
```

---

## 修复建议

### 方案1: 计算 hist1d_mean（推荐）

在 [signal_calculator.py:121](signal_module/signal_calculator.py#L121) 之后添加：

```python
# 更新1天指标移动平均值
hist1d_mean = self.rolling_tracker.update('macd1d', row.get('macd1d', 0))
dif1d_mean = self.rolling_tracker.update('dif1d', row.get('dif1d', 0))
dea1d_mean = self.rolling_tracker.update('dea1d', row.get('dea1d', 0))

hist1d_mean_2 = self.rolling_tracker.update('macd1d_2', row.get('macd1d', 0))
dif1d_mean_2 = self.rolling_tracker.update('dif1d_2', row.get('dif1d', 0))
dea1d_mean_2 = self.rolling_tracker.update('dea1d_2', row.get('dea1d', 0))

row['hist1d_mean'] = hist1d_mean
row['dif1d_mean'] = dif1d_mean
row['dea1d_mean'] = dea1d_mean
row['hist1d_mean_2'] = hist1d_mean_2
row['dif1d_mean_2'] = dif1d_mean_2
row['dea1d_mean_2'] = dea1d_mean_2
```

### 方案2: 禁用1天均值检查（临时方案）

如果不想计算 hist1d_mean，可以设置：

```python
# core/config.py 或环境变量
means_hist1d_count = 0
means_dif1d_count = 0
means_dea1d_count = 0
```

---

## 总结

### 核心问题

**`signal_calculator.py` 缺少1天指标移动平均值的计算代码**

### 拒绝原因

```python
# 配置
means_hist1d_count = 360
hist1d_means_limit = 0

# 实际值
hist1d = -215.47
hist1d_mean = row.get('hist1d_mean', 0)  # = 0 (未计算，使用默认值)

# 检查
-215.47 - 0 < 0  → True  → 拒绝信号
```

### 为什么 macd_refactor.py 不同？

可能：
1. 计算了 hist1d_mean
2. 或者配置中 `means_hist1d_count = 0`
3. 或者使用了不同的数据源

---

**最终答案**: 2024-01-01 19:39:00 的K线数据因为 `hist1d_mean` 未被计算（默认为0），导致 `-215.47 < 0` 的错误检查，信号被拒绝。这是一个**代码bug**，应该在 [signal_calculator.py:121](signal_module/signal_calculator.py#L121) 之后添加1天指标移动平均值的计算代码。
