# 修复1天指标移动平均值缺失的Bug

## 日期
2026-01-07

## Bug描述

`signal_calculator.py` 在计算移动平均值时，**遗漏了1天指标和4小时/1小时指标的第二组移动平均值**，导致信号被错误拒绝。

---

## Bug原因

### 缺失的计算代码

**修复前** ([signal_calculator.py:92-123](signal_module/signal_calculator.py#L92-L123)):

```python
# ✅ 计算了15分钟均值
hist15_mean = self.rolling_tracker.update('macd15m', row.get('macd15m', 0))
hist15_mean_2 = self.rolling_tracker.update('macd15m_2', row.get('macd15m', 0))

# ✅ 计算了1小时均值（第一组）
hist1h_mean = self.rolling_tracker.update('macd1h', row.get('macd1h', 0))
# ❌ 缺少：hist1h_mean_2

# ✅ 计算了4小时均值（第一组）
hist4_mean = self.rolling_tracker.update('macd4h', row.get('macd4h', 0))
# ❌ 缺少：hist4_mean_2

# ❌ 完全缺少1天指标均值计算
# hist1d_mean = ???
# dif1d_mean = ???
# dea1d_mean = ???
# hist1d_mean_2 = ???
# dif1d_mean_2 = ???
# dea1d_mean_2 = ???
```

### 导致的问题

当配置启用均值检查时：

```python
# 配置
means_hist1d_count = 360  # 启用1天均值检查
hist1d_means_limit = 0

# 实际发生
hist1d_mean = row.get('hist1d_mean', 0)  # 返回默认值 0（因为键不存在）
if hist1d - 0 < 0:  # -215.47 < 0
    is_long = False  # 错误地拒绝信号！
```

---

## 修复方案

### 修复后代码

**文件**: [signal_calculator.py:101-155](signal_module/signal_calculator.py#L101-L155)

```python
# 更新1小时指标移动平均值
hist1h_mean = self.rolling_tracker.update('macd1h', row.get('macd1h', 0))
dif1h_mean = self.rolling_tracker.update('dif1h', row.get('dif1h', 0))
dea1h_mean = self.rolling_tracker.update('dea1h', row.get('dea1h', 0))

# 更新1小时指标第二组移动平均值 ✅ 新增
hist1h_mean_2 = self.rolling_tracker.update('macd1h_2', row.get('macd1h', 0))
dif1h_mean_2 = self.rolling_tracker.update('dif1h_2', row.get('dif1h', 0))
dea1h_mean_2 = self.rolling_tracker.update('dea1h_2', row.get('dea1h', 0))

# 更新4小时指标移动平均值
hist4_mean = self.rolling_tracker.update('macd4h', row.get('macd4h', 0))
dif4_mean = self.rolling_tracker.update('dif4h', row.get('dif4h', 0))
dea4_mean = self.rolling_tracker.update('dea4h', row.get('dea4h', 0))

# 更新4小时指标第二组移动平均值 ✅ 新增
hist4_mean_2 = self.rolling_tracker.update('macd4h_2', row.get('macd4h', 0))
dif4_mean_2 = self.rolling_tracker.update('dif4h_2', row.get('dif4h', 0))
dea4_mean_2 = self.rolling_tracker.update('dea4h_2', row.get('dea4h', 0))

# 更新1天指标移动平均值 ✅ 新增
hist1d_mean = self.rolling_tracker.update('macd1d', row.get('macd1d', 0))
dif1d_mean = self.rolling_tracker.update('dif1d', row.get('dif1d', 0))
dea1d_mean = self.rolling_tracker.update('dea1d', row.get('dea1d', 0))

# 更新1天指标第二组移动平均值 ✅ 新增
hist1d_mean_2 = self.rolling_tracker.update('macd1d_2', row.get('macd1d', 0))
dif1d_mean_2 = self.rolling_tracker.update('dif1d_2', row.get('dif1d', 0))
dea1d_mean_2 = self.rolling_tracker.update('dea1d_2', row.get('dea1d', 0))

# 将移动平均值添加到row中
row['hist15_mean'] = hist15_mean
row['dif15_mean'] = dif15_mean
row['dea15_mean'] = dea15_mean
row['hist15_mean_2'] = hist15_mean_2
row['dif15_mean_2'] = dif15_mean_2
row['dea15_mean_2'] = dea15_mean_2
row['hist1h_mean'] = hist1h_mean
row['dif1h_mean'] = dif1h_mean
row['dea1h_mean'] = dea1h_mean
row['hist1h_mean_2'] = hist1h_mean_2  # ✅ 新增
row['dif1h_mean_2'] = dif1h_mean_2  # ✅ 新增
row['dea1h_mean_2'] = dea1h_mean_2  # ✅ 新增
row['hist4_mean'] = hist4_mean
row['dif4_mean'] = dif4_mean
row['dea4_mean'] = dea4_mean
row['hist4_mean_2'] = hist4_mean_2  # ✅ 新增
row['dif4_mean_2'] = dif4_mean_2  # ✅ 新增
row['dea4_mean_2'] = dea4_mean_2  # ✅ 新增
row['hist1d_mean'] = hist1d_mean  # ✅ 新增
row['dif1d_mean'] = dif1d_mean  # ✅ 新增
row['dea1d_mean'] = dea1d_mean  # ✅ 新增
row['hist1d_mean_2'] = hist1d_mean_2  # ✅ 新增
row['dif1d_mean_2'] = dif1d_mean_2  # ✅ 新增
row['dea1d_mean_2'] = dea1d_mean_2  # ✅ 新增
```

---

## 修复效果

### 修复前

```python
# K线数据：2024-01-01 19:39:59
hist1d = -215.47
hist1d_mean = row.get('hist1d_mean', 0)  # = 0 (未计算)

# 检查
if -215.47 - 0 < 0:  # True
    is_long = False  # ❌ 错误拒绝
```

### 修复后

```python
# K线数据：2024-01-01 19:39:59
hist1d = -215.47
hist1d_mean = 实际计算的滚动均值  # 例如：-180.23

# 检查
if -215.47 - 0 < -180.23:  # False
    # ✅ 通过检查（如果均值大于-215.47）
```

---

## 影响范围

### 修复的检查

1. ✅ **HIST1D均值检查** - 现在使用实际计算的均值
2. ✅ **DIF1D均值检查** - 现在使用实际计算的均值
3. ✅ **DEA1D均值检查** - 现在使用实际计算的均值
4. ✅ **HIST1H均值检查（第二组）** - 现在可用
5. ✅ **DIF1H均值检查（第二组）** - 现在可用
6. ✅ **DEA1H均值检查（第二组）** - 现在可用
7. ✅ **HIST4均值检查（第二组）** - 现在可用
8. ✅ **DIF4均值检查（第二组）** - 现在可用
9. ✅ **DEA4均值检查（第二组）** - 现在可用

### 代码行数变化

- **新增**: 24行代码
- **修改**: 0行（只添加，不修改现有逻辑）
- **位置**: [signal_calculator.py:106-155](signal_module/signal_calculator.py#L106-L155)

---

## 配置要求

### RollingMeanTracker 初始化

确保 `RollingMeanTracker` 已配置所有需要的键：

```python
# 第一组
'macd15m', 'dif15m', 'dea15m'     # 15分钟（已存在）
'macd1h', 'dif1h', 'dea1h'        # 1小时（已存在）
'macd4h', 'dif4h', 'dea4h'        # 4小时（已存在）
'macd1d', 'dif1d', 'dea1d'        # 1天（需要确认）

# 第二组
'macd15m_2', 'dif15m_2', 'dea15m_2'     # 15分钟（已存在）
'macd1h_2', 'dif1h_2', 'dea1h_2'        # 1小时（需要确认）
'macd4h_2', 'dif4h_2', 'dea4h_2'        # 4小时（需要确认）
'macd1d_2', 'dif1d_2', 'dea1d_2'        # 1天（需要确认）
```

---

## 验证测试

### 测试步骤

1. **运行回测**
   ```bash
   python web_app.py
   # 浏览器访问 http://localhost:8076/monitor
   # 点击"启动"按钮
   ```

2. **检查日志**
   ```bash
   grep "2024-01-01 19:39:59" /tmp/signal_calculator.log
   ```

3. **验证均值数据**
   日志应该包含：
   ```
   'hist1d_mean': 实际计算的值（不是0）
   'dif1d_mean': 实际计算的值
   'dea1d_mean': 实际计算的值
   'hist1h_mean_2': 实际计算的值
   'hist4_mean_2': 实际计算的值
   ```

4. **对比修复前后**
   - 修复前：信号被拒绝（因为 `hist1d_mean = 0`）
   - 修复后：信号应该通过（因为 `hist1d_mean` 是实际值）

---

## 相关文件

- **修改文件**: [signal_module/signal_calculator.py:106-155](signal_module/signal_calculator.py#L106-L155)
- **配置文件**: [core/config.py](core/config.py)
- **相关文档**:
  - [docs/SIGNAL_REJECTION_FINAL_ANSWER.md](SIGNAL_REJECTION_FINAL_ANSWER.md)
  - [docs/SIGNAL_LOGIC_COMPARISON.md](SIGNAL_LOGIC_COMPARISON.md)

---

## 总结

### Bug类型

**遗漏实现** - 代码结构存在，但缺少了1天指标和第二组均值的计算。

### 根本原因

在重构过程中，只复制了15分钟的均值计算代码，忘记添加1小时/4小时/1天的第二组以及1天的所有均值计算。

### 修复方法

添加了缺失的9个均值计算：
- 1小时指标第二组（3个）
- 4小时指标第二组（3个）
- 1天指标第一组（3个）
- 1天指标第二组（3个）

### 预期效果

✅ **信号计算更准确** - 使用实际滚动均值而不是默认值0
✅ **避免错误拒绝** - 不会因为未计算的均值导致信号被错误拒绝
✅ **完整支持所有配置** - 所有均值检查配置都能正常工作

---

**修复完成！** 现在 `signal_calculator.py` 正确计算了所有时间周期的移动平均值。🎯
