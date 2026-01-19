# 信号拒绝原因的最终结论

## 日期
2026-01-07

## 重要发现

### Web界面参数 vs 代码默认值

**用户提供的准确回测参数**:
```json
"t0_hist1d_limit_min": -9999  // 允许负值
```

**代码默认值** ([core/config.py:109](core/config.py#L109)):
```python
self.T0_HIST1D_LIMIT_MIN = float(os.getenv('T0_HIST1D_LIMIT_MIN', '0'))
```

### 实际运行时使用的值

当从Web界面传入参数时，实际使用的是 `-9999`，而不是代码默认的 `0`！

---

## 重新检查拒绝条件

### HIST1D限制检查 - 通过！

```python
# 使用实际回测参数
t0_hist1d_limit_min = -9999
hist1d = -215.47

# 检查
if hist1d < t0_hist1d_limit_min:
    if -215.47 < -9999:  # False (因为 -215.47 > -9999)
        # ✅ 通过检查！
```

**结论**: HIST1D限制检查**通过**，不是拒绝原因！

---

## 真正的拒绝原因

### HIST1D均值检查 - Bug导致拒绝

**配置参数**:
```json
"means_hist1d_count": 360,      // 启用检查
"hist1d_means_limit": 0          // 限制值
```

**Bug**: `signal_calculator.py` 没有计算 `hist1d_mean`

**检查逻辑** ([signal_calculator.py:335-338](signal_module/signal_calculator.py#L335-L338)):
```python
if is_long and config.MEANS_HIST1D_COUNT != 0:
    hist1d_mean = row.get('hist1d_mean', 0)  # 返回 0（未计算）
    if hist1d - config.HIST1D_MEANS_LIMIT < hist1d_mean:
        is_long = False
        reasons.append(f"HIST1D均值1: {hist1d:.2f} < {hist1d_mean:.2f}")
```

**实际检查**:
```python
hist1d = -215.47
hist1d_means_limit = 0
hist1d_mean = 0  # 未计算，使用默认值

# 检查
if -215.47 - 0 < 0:  # True
    is_long = False  # ❌ 拒绝信号！
```

---

## 总结

### 之前分析的错误

❌ **错误1**: 认为 `t0_hist1d_limit_min = 0`
- **正确**: 实际回测参数是 `-9999`

❌ **错误2**: 认为拒绝原因是 `hist1d < 0`
- **正确**: HIST1D限制检查通过了（`-215.47 > -9999`）

### 正确的拒绝原因

✅ **Bug**: `hist1d_mean` 未被计算，导致均值检查使用默认值0
✅ **拒绝条件**: `-215.47 - 0 < 0` 为True
✅ **原因**: 代码遗漏了1天指标移动平均值的计算

### 修复方案

✅ **已完成**: 在 [signal_calculator.py:117-129](signal_module/signal_calculator.py#L117-L129) 添加了1天指标均值计算

```python
# 更新1天指标移动平均值
hist1d_mean = self.rolling_tracker.update('macd1d', row.get('macd1d', 0))
dif1d_mean = self.rolling_tracker.update('dif1d', row.get('dif1d', 0))
dea1d_mean = self.rolling_tracker.update('dea1d', row.get('dea1d', 0))

# 更新1天指标第二组移动平均值
hist1d_mean_2 = self.rolling_tracker.update('macd1d_2', row.get('macd1d', 0))
dif1d_mean_2 = self.rolling_tracker.update('dif1d_2', row.get('dif1d', 0))
dea1d_mean_2 = self.rolling_tracker.update('dea1d_2', row.get('dea1d', 0))
```

---

## 配置参数说明

### 为什么代码默认值是0？

`core/config.py` 中的默认值是保守的趋势过滤器：

```python
self.T0_HIST1D_LIMIT_MIN = float(os.getenv('T0_HIST1D_LIMIT_MIN', '0'))
```

**含义**: 默认情况下，要求1天MACD柱必须非负（即要求1天级别是上升趋势）

### Web界面参数覆盖

当用户从Web界面传入 `-9999` 时，会覆盖默认值：

```python
# 环境变量或配置文件传入
T0_HIST1D_LIMIT_MIN = -9999  # 允许任何值
```

### 配置来源优先级

1. **Web界面参数** (最高优先级)
2. **环境变量**
3. **代码默认值** (最低优先级)

---

## 验证

### 如何确认实际使用的值？

**方法1**: 查看启动日志

```bash
grep "T0_HIST1D_LIMIT_MIN" /tmp/web_app.log
```

应该看到：
```
T0_HIST1D_LIMIT_MIN: -9999.0  # 使用Web界面参数
# 或
T0_HIST1D_LIMIT_MIN: 0.0      # 使用代码默认值
```

**方法2**: 在配置页面查看

访问 http://localhost:8076/config 查看当前配置

---

## 结论

### 真正的拒绝原因

**Bug**: `signal_calculator.py` 缺少1天指标移动平均值计算
**结果**: `hist1d_mean = 0` (默认值)，导致 `-215.47 < 0` 检查失败
**已修复**: 添加了完整的1天指标均值计算代码

### 配置参数说明

- **代码默认值**: `T0_HIST1D_LIMIT_MIN = 0` (保守策略)
- **实际回测参数**: `t0_hist1d_limit_min = -9999` (从Web界面传入)
- **影响**: 使用 `-9999` 时，HIST1D限制检查会通过

### 修复后的行为

```python
# 修复前
hist1d_mean = 0  # 默认值
if -215.47 - 0 < 0:  # True → 拒绝

# 修复后
hist1d_mean = 实际计算的滚动均值  # 例如 -180.23
if -215.47 - 0 < -180.23:  # False → 通过
```

---

**最终答案**: 信号被拒绝的原因是 `hist1d_mean` 未计算的bug，而不是 `hist1d < 0`。使用 `-9999` 参数时，HIST1D限制检查是通过的。Bug已修复！
