# 信号拒绝原因核对 - 使用准确回测参数

## 日期
2026-01-07

## 用户提供的准确回测参数

```json
{
  "t0_hist1d_limit": 9999,
  "t0_hist1d_limit_min": -9999,  // ← 关键！允许负值
  "t0_dif1d_limit": 9999,
  "t0_dif1d_limit_min": -9999,

  "t0_hist4_limit": 9999,
  "t0_hist4_limit_min": 0,        // ← 要求非负
  "t0_dif4_limit": 1000,
  "t0_dif4_limit_min": -9999,

  "t0_hist1h_limit": 9999,
  "t0_hist1h_limit_min": 0,       // ← 要求非负
  "t0_dif1h_limit": 1000,
  "t0_dif1h_limit_min": -9999,

  "t0_hist15_limit": 9999,
  "t0_hist15_limit_min": 0,       // ← 要求非负
  "t0_dif15_limit": 1000,
  "t0_dif15_limit_min": -9999,

  "means_hist1d_count": 360,
  "means_hist1d_count_2": 0,
  "hist1d_means_limit": 0,
  "hist1d_means_limit_2": 0,
  "means_dif1d_count": 0,
  "means_dif1d_count_2": 120,
  "dif1d_means_limit": 0,
  "dif1d_means_limit_2": 0,
  "means_dea1d_count": 0,
  "dea1d_means_limit": 0,
  "dea1d_means_limit_2": 0
}
```

---

## K线数据 (2024-01-01 19:39:59)

```python
hist15 = 53.64   # 15分钟MACD柱
dif15 = 159.37   # 15分钟DIF
dea15 = 105.73   # 15分钟DEA

hist1h = 68.48   # 1小时MACD柱
dif1h = 153.70   # 1小时DIF
dea1h = 85.22    # 1小时DEA

hist4 = 116.09   # 4小时MACD柱
dif4 = 34.01     # 4小时DIF
dea4 = -82.07    # 4小时DEA

hist1d = -215.47 # 1天MACD柱 (负值)
dif1d = 596.34   # 1天DIF
dea1d = 811.81   # 1天DEA
```

---

## 逐步检查所有条件

### ✅ 1. 15分钟指标检查

**HIST15限制**:
```python
检查: hist15 < t0_hist15_limit_min
检查: 53.64 < 0
结果: False ✅ 通过
```

**DIF15限制**:
```python
检查: dif15 < t0_dif15_limit_min
检查: 159.37 < -9999
结果: False ✅ 通过
```

**HIST15均值检查**:
```python
means_hist15_count = 5
hist15_means_limit = 1
检查: hist15 - hist15_means_limit < hist15_mean
检查: 53.64 - 1 < hist15_mean
需要数据库中的 hist15_mean 值
```

---

### ✅ 2. 1小时指标检查

**HIST1H限制**:
```python
检查: hist1h < t0_hist1h_limit_min
检查: 68.48 < 0
结果: False ✅ 通过
```

**DIF1H限制**:
```python
检查: dif1h < t0_dif1h_limit_min
检查: 153.70 < -9999
结果: False ✅ 通过
```

**HIST1H均值检查**:
```python
means_hist1h_count = 5
hist1h_means_limit = 1
检查: hist1h - hist1h_means_limit < hist1h_mean
检查: 68.48 - 1 < hist1h_mean
需要数据库中的 hist1h_mean 值
```

---

### ❌ 3. 4小时指标检查

**HIST4限制**:
```python
检查: hist4 < t0_hist4_limit_min
检查: 116.09 < 0
结果: False ✅ 通过
```

**DIF4限制**:
```python
检查: dif4 < t0_dif4_limit_min
检查: 34.01 < -9999
结果: False ✅ 通过
```

**HIST4均值检查**:
```python
means_hist4_count = 5
hist4_means_limit = 1
检查: hist4 - hist4_means_limit < hist4_mean
检查: 116.09 - 1 < hist4_mean
需要数据库中的 hist4_mean 值
```

---

### ✅ 4. 1天指标检查

**HIST1D限制**:
```python
检查: hist1d < t0_hist1d_limit_min
检查: -215.47 < -9999
结果: False ✅ 通过！
```

**重要**: `t0_hist1d_limit_min = -9999`，所以 `hist1d = -215.47` **通过了限制检查**！

**DIF1D限制**:
```python
检查: dif1d < t0_dif1d_limit_min
检查: 596.34 < -9999
结果: False ✅ 通过
```

**HIST1D均值检查** - **这是关键！**
```python
means_hist1d_count = 360        // ← 启用！
hist1d_means_limit = 0          // ← 限制值为0

检查: hist1d - hist1d_means_limit < hist1d_mean
检查: -215.47 - 0 < hist1d_mean
检查: -215.47 < hist1d_mean

如果 hist1d_mean <= -215.47，则拒绝信号！
```

---

## 关键发现：HIST1D均值检查

### 配置参数

```python
means_hist1d_count = 360        // 检查过去360个1天MACD柱的均值
hist1d_means_limit = 0          // 限制值为0
```

### 检查逻辑

[signal_calculator.py:334-338](signal_module/signal_calculator.py#L334-L338):
```python
if is_long and config.MEANS_HIST1D_COUNT != 0:
    hist1d_mean = row.get('hist1d_mean', 0)
    if hist1d - config.HIST1D_MEANS_LIMIT < hist1d_mean:
        is_long = False
        reasons.append(f"HIST1D均值1: {hist1d:.2f} < {hist1d_mean:.2f}")
```

### 拒绝条件

```python
# 当前值
hist1d = -215.47
hist1d_means_limit = 0

# 检查
hist1d - hist1d_means_limit < hist1d_mean
-215.47 - 0 < hist1d_mean
-215.47 < hist1d_mean

# 如果 hist1d_mean <= -215.47，则拒绝信号
```

---

## 需要查询数据库确认

### 查询 hist1d_mean 值

```bash
sqlite3 data/klines.db "
SELECT
    close_time,
    macd1d,
    hist1d_mean,
    hist1d_mean_2,
    dif1d_mean,
    dif1d_mean_2
FROM klines_1m_macd_smooth_ma
WHERE close_time = '2024-01-01 19:39:59.999000+00:00';
"
```

---

## 最可能的拒绝原因

### 条件1: HIST1D均值检查

**配置**:
- `means_hist1d_count = 360` (启用)
- `hist1d_means_limit = 0`

**检查**:
```python
if -215.47 - 0 < hist1d_mean:
    拒绝信号
```

**如果 `hist1d_mean <= -215.47`，则拒绝！**

这意味着：如果过去360个1天MACD柱的均值 <= -215.47，则拒绝开仓。

这是一个合理的趋势过滤器：**当前值低于历史均值时，不开多仓**。

---

## 总结

### 之前的分析错误

我之前认为拒绝原因是 `hist1d < t0_hist1d_limit_min`（即 -215.47 < 0），但这是**错误的**！

根据准确的回测参数：
```json
"t0_hist1d_limit_min": -9999  // 允许负值
```

所以 `hist1d = -215.47` **通过了限制检查**！

### 真正的拒绝原因

最可能是 **HIST1D均值检查** 拒绝了信号：

```python
means_hist1d_count = 360
hist1d_means_limit = 0

检查: hist1d - 0 < hist1d_mean
检查: -215.47 < hist1d_mean

如果 hist1d_mean <= -215.47，则拒绝
```

### 其他可能的拒绝条件

1. **HIST15均值检查** - 需要查询 `hist15_mean` 值
2. **HIST1H均值检查** - 需要查询 `hist1h_mean` 值
3. **HIST4均值检查** - 需要查询 `hist4_mean` 值
4. **DIF15/DIF1H/DIF4均值检查** - 需要查询对应的均值

---

## 下一步

### 查询完整的均值数据

```bash
sqlite3 data/klines.db "
SELECT
    close_time,
    hist15_mean, hist15_mean_2,
    dif15_mean, dif15_mean_2,
    dea15_mean, dea15_mean_2,
    hist1h_mean, hist1h_mean_2,
    dif1h_mean, dif1h_mean_2,
    dea1h_mean, dea1h_mean_2,
    hist4_mean, hist4_mean_2,
    dif4_mean, dif4_mean_2,
    dea4_mean, dea4_mean_2,
    hist1d_mean, hist1d_mean_2,
    dif1d_mean, dif1d_mean_2,
    dea1d_mean, dea1d_mean_2
FROM klines_1m_macd_smooth_ma
WHERE close_time = '2024-01-01 19:39:59.999000+00:00';
"
```

### 添加调试日志

在 signal_calculator.py 中添加详细日志，输出每个检查的结果。

---

**结论**: 需要查询数据库中的均值数据才能确定确切的拒绝原因。最可能是 HIST1D均值检查 拒绝了信号。
