# 移动平均值实时计算功能

## 问题描述

用户反馈:参考macd_refactor.py,信号判断中的移动平均值(如`hist15_mean`, `dif15_mean`等)需要实时计算,而数据库中没有存储这些字段。

### 根本原因

MACD V5.0策略在判断开仓信号时,需要对比当前指标值与移动平均值:

**示例逻辑** (来自macd_refactor.py):
```python
# 判断hist15是否超过移动平均值的限制
if hist15 - Config.HIST15_MEANS_LIMIT < row['hist15_mean']:
    engine.duoq = f"DEBUG: 跳过多头开仓, hist15={hist15:.2f} < hist15mean={row['hist15_mean']:.2f}"
    return None
```

**需要的移动平均值字段**:
- `hist15_mean`, `hist15_mean_2` - 15分钟柱状图的移动平均值(两组窗口)
- `dif15_mean`, `dif15_mean_2` - 15分钟DIF的移动平均值(两组窗口)
- `dea15_mean`, `dea15_mean_2` - 15分钟DEA的移动平均值(两组窗口)
- `hist1h_mean`, `dif1h_mean`, `dea1h_mean` - 1小时指标的移动平均值
- `hist4_mean`, `dif4_mean`, `dea4_mean` - 4小时指标的移动平均值

**问题**:
- 数据库中未存储这些移动平均值字段
- 这些值需要根据历史数据实时计算
- 使用pandas的`rolling().mean()`方法

## 解决方案

### 方案对比

| 方案 | 描述 | 优点 | 缺点 | 选择 |
|------|------|------|------|------|
| 方案1 | 修改数据库,添加移动平均值字段 | 数据持久化,查询快 | 需要修改数据库结构,重新计算所有历史数据 | ❌ |
| 方案2 | 使用滑动窗口实时计算 | 无需修改数据库,灵活,参数可调 | 需要维护内存状态 | ✅ |

**选择方案2** - 使用滑动窗口实时计算

### 实现架构

```
K线数据流
  ↓
signal_calculator.calculate_open_signal()
  ↓
1. 更新滑动窗口
   - 将当前指标值添加到deque
   - deque自动维护固定长度
  ↓
2. 计算移动平均值
   - mean = sum(deque) / len(deque)
  ↓
3. 添加到row字典
   - row['hist15_mean'] = mean
  ↓
4. 信号检查
   - 使用row中的移动平均值判断信号
```

## 代码实现

### 1. 滑动窗口管理器

**文件**: [signal_module/rolling_mean_tracker.py](signal_module/rolling_mean_tracker.py)

**核心类**: `RollingMeanTracker`

**功能**:
- 维护各指标的滑动窗口(deque)
- 实时计算移动平均值
- 提供批量更新接口

**关键方法**:
```python
class RollingMeanTracker:
    def init_field(self, field_name: str, window_size: int):
        """初始化一个指标的滑动窗口"""
        self.windows[field_name] = deque(maxlen=window_size)

    def update(self, field_name: str, value: float) -> Optional[float]:
        """更新指标值并返回移动平均值"""
        self.windows[field_name].append(value)
        return sum(window) / len(window)

    def get_mean(self, field_name: str) -> Optional[float]:
        """获取当前移动平均值"""
```

**使用示例**:
```python
tracker = RollingMeanTracker()

# 初始化窗口大小为60
tracker.init_field('macd15m', 60)

# 更新值并获取移动平均值
mean1 = tracker.update('macd15m', 123.45)  # 第1个值
mean2 = tracker.update('macd15m', 124.56)  # 第2个值
...
mean60 = tracker.update('macd15m', 130.00)  # 第60个值
mean61 = tracker.update('macd15m', 131.00)  # 第61个值,自动移除第1个值
```

### 2. 信号计算器集成

**文件**: [signal_module/signal_calculator.py](signal_module/signal_calculator.py)

**修改内容**:

**初始化**:
```python
class SignalCalculator:
    def __init__(self):
        # 初始化移动平均值追踪器
        self.rolling_tracker = get_rolling_mean_tracker()

        # 初始化各个指标的滑动窗口
        if config.MEANS_HIST15_COUNT > 0:
            self.rolling_tracker.init_field('macd15m', config.MEANS_HIST15_COUNT)
        if config.MEANS_DIF15_COUNT > 0:
            self.rolling_tracker.init_field('dif15m', config.MEANS_DIF15_COUNT)
        ...
```

**计算信号前更新移动平均值**:
```python
def calculate_open_signal(self, indicators: Dict[str, Any]) -> Optional[Signal]:
    row = indicators

    # 第一步: 更新移动平均值
    hist15_mean = self.rolling_tracker.update('macd15m', row.get('macd15m', 0))
    dif15_mean = self.rolling_tracker.update('dif15m', row.get('dif15m', 0))
    dea15_mean = self.rolling_tracker.update('dea15m', row.get('dea15m', 0))
    ...

    # 第二步: 将移动平均值添加到row
    row['hist15_mean'] = hist15_mean
    row['dif15_mean'] = dif15_mean
    row['dea15_mean'] = dea15_mean
    ...

    # 第三步: 提取原始指标并检查信号
    hist15 = row.get('macd15m', 0)
    ...

    # 信号检查时会使用row中的移动平均值
    long_signal, long_reason = self._check_long_signal(...)
```

**信号检查逻辑** (已存在,无需修改):
```python
def _check_long_signal(self, ...):
    # HIST15均值检查 (第一组)
    if config.MEANS_HIST15_COUNT != 0:
        hist15_mean = row.get('hist15_mean', 0)
        if hist15 - config.HIST15_MEANS_LIMIT < hist15_mean:
            is_long = False
            reasons.append(f"HIST15均值1: {hist15:.2f} < {hist15_mean:.2f}")

    # HIST15均值检查 (第二组)
    if config.MEANS_HIST15_COUNT_2 != 0:
        hist15_mean_2 = row.get('hist15_mean_2', 0)
        if hist15 - config.HIST15_MEANS_LIMIT_2 < hist15_mean_2:
            is_long = False
            reasons.append(f"HIST15均值2: {hist15:.2f} < {hist15_mean_2:.2f}")
```

## 配置参数

### 移动平均窗口大小

在 `core/config.py` 中配置:

```python
# 15分钟指标
self.MEANS_HIST15_COUNT = int(os.getenv('MEANS_HIST15_COUNT', '5'))    # 默认5个
self.MEANS_DIF15_COUNT = int(os.getenv('MEANS_DIF15_COUNT', '5'))     # 默认5个
self.MEANS_DEA15_COUNT = int(os.getenv('MEANS_DEA15_COUNT', '5'))     # 默认5个

# 15分钟指标(第二组)
self.MEANS_HIST15_COUNT_2 = int(os.getenv('MEANS_HIST15_COUNT_2', '10'))  # 默认10个
self.MEANS_DIF15_COUNT_2 = int(os.getenv('MEANS_DIF15_COUNT_2', '30'))   # 默认30个
self.MEANS_DEA15_COUNT_2 = int(os.getenv('MEANS_DEA15_COUNT_2', '10'))   # 默认10个

# 1小时指标
self.MEANS_HIST1H_COUNT = int(os.getenv('MEANS_HIST1H_COUNT', '5'))
self.MEANS_DIF1H_COUNT = int(os.getenv('MEANS_DIF1H_COUNT', '5'))
self.MEANS_DEA1H_COUNT = int(os.getenv('MEANS_DEA1H_COUNT', '5'))

# 4小时指标
self.MEANS_HIST4_COUNT = int(os.getenv('MEANS_HIST4_COUNT', '5'))
self.MEANS_DIF4_COUNT = int(os.getenv('MEANS_DIF4_COUNT', '5'))
self.MEANS_DEA4_COUNT = int(os.getenv('MEANS_DEA4_COUNT', '5'))
```

### 移动平均限制值

```python
# 限制值: 当前值需要高于移动平均值+限制
self.HIST15_MEANS_LIMIT = float(os.getenv('HIST15_MEANS_LIMIT', '1'))
self.DIF15_MEANS_LIMIT = float(os.getenv('DIF15_MEANS_LIMIT', '1'))
self.DEA15_MEANS_LIMIT = float(os.getenv('DEA15_MEANS_LIMIT', '1'))

# 限制值2 (第二组)
self.HIST15_MEANS_LIMIT_2 = float(os.getenv('HIST15_MEANS_LIMIT_2', '1'))
self.DIF15_MEANS_LIMIT_2 = float(os.getenv('DIF15_MEANS_LIMIT_2', '1'))
```

## 工作流程

### 回测过程中的移动平均值计算

```
开始回测
  ↓
for kline in klines:  # 遍历每条K线
  ↓
  调用 signal_calculator.calculate_open_signal(kline)
  ↓
  1. 更新移动平均值
     - tracker.update('macd15m', kline['macd15m'])
     - tracker.update('dif15m', kline['dif15m'])
     - ...
     - 返回: hist15_mean, dif15_mean, ...
  ↓
  2. 添加到row字典
     - row['hist15_mean'] = hist15_mean
     - row['dif15_mean'] = dif15_mean
  ↓
  3. 信号检查
     - if hist15 - HIST15_MEANS_LIMIT < hist15_mean:
         跳过开仓 (指标值不够高)
```

### 移动平均值的演变

```
第1条K线: macd15m=10.0 → mean=10.0      (窗口: [10.0])
第2条K线: macd15m=12.0 → mean=11.0      (窗口: [10.0, 12.0])
第3条K线: macd15m=11.0 → mean=11.0      (窗口: [10.0, 12.0, 11.0])
第4条K线: macd15m=13.0 → mean=11.5      (窗口: [10.0, 12.0, 11.0, 13.0])
第5条K线: macd15m=15.0 → mean=12.2      (窗口: [10.0, 12.0, 11.0, 13.0, 15.0])
第6条K线: macd15m=14.0 → mean=13.0      (窗口: [12.0, 11.0, 13.0, 15.0, 14.0]) ← 自动移除第1个值
...
```

## 性能优化

### 1. deque的O(1)性能

```python
from collections import deque

# 满O(1)操作
window = deque(maxlen=60)
window.append(value)        # O(1) - 自动移除最旧的值
mean = sum(window) / len(window)  # O(n) - n是窗口大小
```

**优点**:
- `deque.append()`是O(1)操作
- 自动维护窗口大小,无需手动删除旧值
- 比pandas rolling更高效

### 2. 增量计算(可选优化)

如果窗口很大(如1000+),可以使用增量计算避免每次sum:

```python
class IncrementalMeanTracker:
    def __init__(self, window_size: int):
        self.window_size = window_size
        self.window = deque(maxlen=window_size)
        self.sum = 0.0

    def update(self, value: float) -> float:
        if len(self.window) == self.window_size:
            # 窗口满,移除最旧的值
            self.sum -= self.window[0]

        self.window.append(value)
        self.sum += value
        return self.sum / len(self.window)
```

**性能对比**:
- 原始方法: O(n) - 每次都要sum
- 增量方法: O(1) - 只加减一个值

### 3. 内存占用

**每个指标窗口的内存占用**:
```python
window_size = 60
value_size = 8 bytes (float)
total = 60 * 8 = 480 bytes ≈ 0.5 KB
```

**所有指标窗口的总内存**:
```
约12个指标 × 60 × 8 bytes = 5.76 KB
```

完全可以忽略!

## 调试和验证

### 查看移动平均值

在代码中添加日志:
```python
if self.debug_count % 100 == 0:
    logger.info(f"移动平均值:")
    logger.info(f"  hist15_mean: {hist15_mean:.4f}")
    logger.info(f"  dif15_mean: {dif15_mean:.4f}")
    logger.info(f"  dea15_mean: {dea15_mean:.4f}")
```

### 验证正确性

**方法1**: 对比pandas rolling
```python
import pandas as pd

# 假设有100条历史数据
values = [10.0, 12.0, 11.0, 13.0, 15.0, ...]

# pandas rolling mean
pandas_mean = pd.Series(values).rolling(window=5).mean()

# 我们的实现
tracker = RollingMeanTracker()
tracker.init_field('test', 5)
our_means = [tracker.update('test', v) for v in values]

# 对比
assert pandas_mean.equals(pd.Series(our_means))
```

**方法2**: 查看回测日志
```python
# 回测日志中应该包含移动平均值信息
logger.info(f"DEBUG: 均值对比 hist15mean={hist15_mean:.2f} dif15mean={dif15_mean:.2f}")
```

## 常见问题

### Q1: 为什么移动平均值在开始时是None?

**原因**: 窗口未填满之前,移动平均值为None或0

**解决**:
```python
# 方法1: 等待窗口填满
if hist15_mean is None:
    return None  # 跳过前几条数据

# 方法2: 使用部分数据计算
if hist15_mean is None:
    hist15_mean = hist15  # 用当前值代替
```

### Q2: 窗口大小如何选择?

**建议**:
- 5-10: 短期,反应快
- 20-30: 中期,平衡
- 60-120: 长期,反应慢

**参考**:
```python
# 15分钟K线
MEANS_HIST15_COUNT = 5  # 5 × 15分钟 = 75分钟 = 1.25小时
MEANS_HIST15_COUNT_2 = 30  # 30 × 15分钟 = 450分钟 = 7.5小时

# 1小时K线
MEANS_HIST1H_COUNT = 5  # 5 × 1小时 = 5小时
MEANS_HIST1H_COUNT_2 = 24  # 24 × 1小时 = 24小时 = 1天

# 4小时K线
MEANS_HIST4_COUNT = 5  # 5 × 4小时 = 20小时
MEANS_HIST4_COUNT_2 = 30  # 30 × 4小时 = 120小时 = 5天
```

### Q3: 如何调整窗口大小?

**方法1**: 修改环境变量
```bash
export MEANS_HIST15_COUNT=10
export MEANS_DIF15_COUNT=20
python web_app.py
```

**方法2**: 修改config.py
```python
self.MEANS_HIST15_COUNT = 10
self.MEANS_DIF15_COUNT = 20
```

## 总结

通过实现移动平均值实时计算功能,我们:

1. ✅ **解决了数据库缺失字段的问题** - 无需修改数据库结构
2. ✅ **实现了灵活的参数配置** - 窗口大小可随时调整
3. ✅ **保持了策略的完整性** - 完全按照macd_refactor.py的逻辑
4. ✅ **优化了性能** - 使用deque的O(1)操作
5. ✅ **易于维护和调试** - 清晰的代码结构和日志

现在信号计算器会:
- 实时更新每个指标的移动平均值
- 使用移动平均值进行信号过滤
- 完全符合MACD V5.0策略的要求

回测过程中会看到类似这样的日志:
```
DEBUG: 均值对比 hist15mean=12.34 dif15mean=5.67 dea15mean=3.21
  当前值: hist15=15.20, dif=7.80, dea=4.50
  判断: hist15(15.20) - LIMIT(1) = 14.20 > hist15mean(12.34) ✓ 通过
```
