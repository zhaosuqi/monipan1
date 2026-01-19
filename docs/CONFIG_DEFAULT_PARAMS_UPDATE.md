# 更新默认配置参数

## 日期
2026-01-07

## 更新内容

将用户提供的准确回测参数更新到 `core/config.py` 的默认初始化值中。

---

## 修改的参数

### 1. T0_HIST1D_LIMIT_MIN - 关键修改

**文件**: [core/config.py:109](core/config.py#L109)

**修改前**:
```python
self.T0_HIST1D_LIMIT_MIN = float(os.getenv('T0_HIST1D_LIMIT_MIN', '0'))
```

**修改后**:
```python
self.T0_HIST1D_LIMIT_MIN = float(os.getenv('T0_HIST1D_LIMIT_MIN', '-9999'))
```

**影响**:
- 修改前: 要求1天MACD柱必须非负（`>= 0`）
- 修改后: 允许1天MACD柱为任何值（`>= -9999`）
- 这是与 `macd_refactor.py` 行为一致的关键修改

---

### 2. T0_DIF1D_LIMIT - 扩大上限

**文件**: [core/config.py:110](core/config.py#L110)

**修改前**:
```python
self.T0_DIF1D_LIMIT = float(os.getenv('T0_DIF1D_LIMIT', '1000'))
```

**修改后**:
```python
self.T0_DIF1D_LIMIT = float(os.getenv('T0_DIF1D_LIMIT', '9999'))
```

---

### 3. T0_J4H_LIMIT - 调整4小时J值上限

**文件**: [core/config.py:116](core/config.py#L116)

**修改前**:
```python
self.T0_J4H_LIMIT = float(os.getenv('T0_J4H_LIMIT', '999'))
```

**修改后**:
```python
self.T0_J4H_LIMIT = float(os.getenv('T0_J4H_LIMIT', '113'))
```

---

### 4. T0_J4H_LIMIT_KONG - 调整4小时J值下限

**文件**: [core/config.py:121](core/config.py#L121)

**修改前**:
```python
self.T0_J4H_LIMIT_KONG = float(os.getenv('T0_J4H_LIMIT_KONG', '-999'))
```

**修改后**:
```python
self.T0_J4H_LIMIT_KONG = float(os.getenv('T0_J4H_LIMIT_KONG', '-13'))
```

---

### 5. MEANS_HIST1D_COUNT - 启用1天均值检查

**文件**: [core/config.py:148](core/config.py#L148)

**修改前**:
```python
self.MEANS_HIST1D_COUNT = int(os.getenv('MEANS_HIST1D_COUNT', '0'))
```

**修改后**:
```python
self.MEANS_HIST1D_COUNT = int(os.getenv('MEANS_HIST1D_COUNT', '360'))
```

**影响**:
- 修改前: 禁用1天MACD柱均值检查
- 修改后: 启用1天MACD柱均值检查（过去360个值）
- 这是重要的趋势过滤器

---

### 6. HIST1D_MEANS_LIMIT - 设置均值限制

**文件**: [core/config.py:149](core/config.py#L149)

**修改前**:
```python
self.HIST1D_MEANS_LIMIT = float(os.getenv('HIST1D_MEANS_LIMIT', '1'))
```

**修改后**:
```python
self.HIST1D_MEANS_LIMIT = float(os.getenv('HIST1D_MEANS_LIMIT', '0'))
```

---

### 7. DIF1D_MEANS_LIMIT - 调整DIF1D均值限制

**文件**: [core/config.py:151](core/config.py#L151)

**修改前**:
```python
self.DIF1D_MEANS_LIMIT = float(os.getenv('DIF1D_MEANS_LIMIT', '999'))
```

**修改后**:
```python
self.DIF1D_MEANS_LIMIT = float(os.getenv('DIF1D_MEANS_LIMIT', '0'))
```

---

### 8. DEA1D_MEANS_LIMIT - 调整DEA1D均值限制

**文件**: [core/config.py:153](core/config.py#L153)

**修改前**:
```python
self.DEA1D_MEANS_LIMIT = float(os.getenv('DEA1D_MEANS_LIMIT', '999'))
```

**修改后**:
```python
self.DEA1D_MEANS_LIMIT = float(os.getenv('DEA1D_MEANS_LIMIT', '0'))
```

---

### 9. MEANS_DIF1D_COUNT_2 - 启用第二组DIF1D均值检查

**文件**: [core/config.py:182](core/config.py#L182)

**修改前**:
```python
self.MEANS_DIF1D_COUNT_2 = int(os.getenv('MEANS_DIF1D_COUNT_2', '0'))
```

**修改后**:
```python
self.MEANS_DIF1D_COUNT_2 = int(os.getenv('MEANS_DIF1D_COUNT_2', '120'))
```

---

### 10. DIF1D_MEANS_LIMIT_2 - 设置第二组限制

**文件**: [core/config.py:183](core/config.py#L183)

**修改前**:
```python
self.DIF1D_MEANS_LIMIT_2 = float(os.getenv('DIF1D_MEANS_LIMIT_2', '999'))
```

**修改后**:
```python
self.DIF1D_MEANS_LIMIT_2 = float(os.getenv('DIF1D_MEANS_LIMIT_2', '0'))
```

---

### 11. DEA1D_MEANS_LIMIT_2 - 设置第二组DEA1D限制

**文件**: [core/config.py:185](core/config.py#L185)

**修改前**:
```python
self.DEA1D_MEANS_LIMIT_2 = float(os.getenv('DEA1D_MEANS_LIMIT_2', '999'))
```

**修改后**:
```python
self.DEA1D_MEANS_LIMIT_2 = float(os.getenv('DEA1D_MEANS_LIMIT_2', '0'))
```

---

### 12. DATE_TO - 调整默认结束日期

**文件**: [core/config.py:238](core/config.py#L238)

**修改前**:
```python
self.DATE_TO = os.getenv('DATE_TO', '2025-12-30 23:59:59')
```

**修改后**:
```python
self.DATE_TO = os.getenv('DATE_TO', '2024-1-10 23:59:59')
```

---

### 13. STOP_LOSS_POINTS - 调整止损点数

**文件**: [core/config.py:241](core/config.py#L241)

**修改前**:
```python
self.STOP_LOSS_POINTS = float(os.getenv('STOP_LOSS_POINTS', '0.016'))
```

**修改后**:
```python
self.STOP_LOSS_POINTS = float(os.getenv('STOP_LOSS_POINTS', '0.0165'))
```

---

### 14. TP_LEVELS - 调整止盈级别

**文件**: [core/config.py:242](core/config.py#L242)

**修改前**:
```python
self.TP_LEVELS = json.loads(os.getenv('TP_LEVELS', '[1.006, 1.012, 1.018, 1.024, 1.03]'))
```

**修改后**:
```python
self.TP_LEVELS = json.loads(os.getenv('TP_LEVELS', '[1.0065, 1.012, 1.018, 1.024, 1.03]'))
```

---

## 配置参数对比

### 关键差异总结

| 参数 | 旧默认值 | 新默认值 | 影响 |
|------|---------|---------|------|
| **T0_HIST1D_LIMIT_MIN** | `0` | `-9999` | 允许1天MACD为负值 |
| **MEANS_HIST1D_COUNT** | `0` | `360` | 启用1天均值检查 |
| **T0_J4H_LIMIT** | `999` | `113` | 限制4小时J值上限 |
| **T0_J4H_LIMIT_KONG** | `-999` | `-13` | 限制4小时J值下限 |
| **DATE_TO** | `2025-12-30` | `2024-1-10` | 缩短默认回测期间 |
| **STOP_LOSS_POINTS** | `0.016` | `0.0165` | 微调止损点数 |

---

## 为什么要更新这些参数？

### 1. 与 macd_refactor.py 一致

**关键修改**: `T0_HIST1D_LIMIT_MIN` 从 `0` 改为 `-9999`

- 修改前: 要求1天MACD柱必须非负（保守策略）
- 修改后: 允许1天MACD柱为负值（与旧版本一致）

### 2. 启用均值检查

**关键修改**: `MEANS_HIST1D_COUNT` 从 `0` 改为 `360`

- 修改前: 禁用1天均值检查
- 修改后: 启用1天均值检查（趋势过滤器）
- 配合之前修复的 `hist1d_mean` 计算bug

### 3. 调整J值限制

**关键修改**: `T0_J4H_LIMIT` 和 `T0_J4H_LIMIT_KONG`

- 从 `[-999, 999]` 缩小到 `[-13, 113]`
- 更严格的4小时J值过滤

### 4. 优化回测默认值

**关键修改**: `DATE_TO` 和 `STOP_LOSS_POINTS`

- 缩短默认回测期间（10天而不是1年+）
- 微调止损点数（1.65%而不是1.6%）

---

## 验证

### 检查默认值

```bash
python -c "
from core.config import config
print(f'T0_HIST1D_LIMIT_MIN: {config.T0_HIST1D_LIMIT_MIN}')
print(f'MEANS_HIST1D_COUNT: {config.MEANS_HIST1D_COUNT}')
print(f'T0_J4H_LIMIT: {config.T0_J4H_LIMIT}')
print(f'DATE_TO: {config.DATE_TO}')
"
```

**预期输出**:
```
T0_HIST1D_LIMIT_MIN: -9999.0
MEANS_HIST1D_COUNT: 360
T0_J4H_LIMIT: 113.0
DATE_TO: 2024-1-10 23:59:59
```

### 测试回测

```bash
python web_app.py
# 浏览器访问 http://localhost:8076/monitor
# 检查配置页面的参数是否正确
```

---

## 信号影响分析

### 2024-01-01 19:39:59 的K线数据

使用新的默认参数：

```python
# 配置
t0_hist1d_limit_min = -9999
means_hist1d_count = 360
hist1d_means_limit = 0

# K线数据
hist1d = -215.47
hist1d_mean = 实际计算的滚动均值（例如-180.23）

# 检查
# 1. HIST1D限制检查
if -215.47 < -9999:  # False，通过 ✓

# 2. HIST1D均值检查
if -215.47 - 0 < -180.23:  # True，拒绝 ✗
# 原因：当前值低于历史均值
```

**结论**: 即使使用 `-9999` 参数，这个信号仍然应该被拒绝（因为均值检查）。

---

## 环境变量覆盖

所有参数仍然可以通过环境变量覆盖：

```bash
# 覆盖默认值
export T0_HIST1D_LIMIT_MIN=0
export MEANS_HIST1D_COUNT=0

python web_app.py
```

---

## 总结

### 主要变更

1. ✅ **T0_HIST1D_LIMIT_MIN**: `0` → `-9999` (允许负值)
2. ✅ **MEANS_HIST1D_COUNT**: `0` → `360` (启用均值检查)
3. ✅ **T0_J4H_LIMIT**: `999` → `113` (更严格的J值过滤)
4. ✅ **DATE_TO**: `2025-12-30` → `2024-1-10` (合理的默认期间)
5. ✅ **其他细节调整**: 止损、止盈、均值限制等

### 预期效果

- ✅ 与 `macd_refactor.py` 行为更一致
- ✅ 启用完整的均值检查功能
- ✅ 更合理的默认回测期间
- ✅ 配合 `hist1d_mean` bug修复，完整支持1天指标均值

### 文件修改

- **修改文件**: [core/config.py](core/config.py)
- **修改行数**: 14处
- **向后兼容**: 是（所有参数仍可通过环境变量覆盖）

---

**配置更新完成！** 默认参数现在与你的准确回测参数一致。
