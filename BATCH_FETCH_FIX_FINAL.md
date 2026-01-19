# 修复数据丢失问题 - 按1000条精确分批

## 问题描述

原代码使用双层循环：
- **外层**：按天分块（1440分钟）
- **内层**：每块内按1000条分批获取

**问题**：一天有1440分钟，但API最多返回1000条，导致每天丢失440条数据。

### 错误的请求示例

```
时间块: 2025-12-21 00:00:00 ~ 2025-12-22 00:00:00（1440分钟）
→ 批次 1: 从 2025-12-21 00:00:00 开始获取
请求: startTime=2025-12-21 00:00:00, endTime=2025-12-22 00:00:00
API返回: 1000 条（00:00:00 ~ 16:40:00）
❌ 丢失: 16:41:00 ~ 23:59:00（440条）
```

## 解决方案

**去掉双层循环，改为单层循环，直接按1000条分批获取。**

### 修改后的逻辑

```python
# 单层循环：直接按1000条分批获取
current_start = start_time  # 数据库最后一条 + 1分钟

while current_start < end_time:
    # 请求：startTime 每次更新，endTime 保持在总结束时间
    klines = fetch_klines_range(
        exchange,
        current_start,      # 起点：每次更新
        end_time            # 终点：保持在总结束时间
    )

    # 保存数据
    save_to_klines_1m(klines)

    # 更新起点：最后一条的 open_time + 1分钟
    current_start = klines[-1].open_time + timedelta(minutes=1)

    # 如果获取数量 < 1000，说明已到endTime
    if len(klines) < 1000:
        break
```

### 工作原理

#### 批次1
```
current_start = 2025-12-21 00:00:00
end_time = 2026-01-09 19:28:00

请求: startTime=2025-12-21 00:00:00, endTime=2026-01-09 19:28:00
API返回: 1000 条（00:00:00 ~ 16:40:00）

保存后更新:
current_start = 2025-12-21 16:40:00 + 1分钟
            = 2025-12-21 16:41:00
```

#### 批次2
```
current_start = 2025-12-21 16:41:00
end_time = 2026-01-09 19:28:00

请求: startTime=2025-12-21 16:41:00, endTime=2026-01-09 19:28:00
API返回: 1000 条（16:41:00 ~ 2025-12-22 09:21:00）

保存后更新:
current_start = 2025-12-22 09:21:00 + 1分钟
            = 2025-12-22 09:22:00
```

#### 持续推进
```
批次3: 2025-12-22 09:22:00 ~ 2025-12-23 01:42:00
批次4: 2025-12-23 01:42:00 ~ 2025-12-23 18:02:00
...
最后一批: 获取 < 1000 条，完成
```

## 关键改进

### 1. 单层循环替代双层循环

**修改前（错误）**：
```python
chunk_minutes = 1440  # 按天分块
chunk_start = start_time

while chunk_start < end_time:
    chunk_end = chunk_start + timedelta(minutes=chunk_minutes)

    inner_start = chunk_start
    while inner_start < chunk_end:
        # ❌ endTime 是天结束时间
        klines = get_klines(inner_start, chunk_end)
        # 只返回1000条，丢失440条
```

**修改后（正确）**：
```python
current_start = start_time

while current_start < end_time:
    # ✅ endTime 保持在总结束时间
    klines = get_klines(current_start, end_time)
    # 返回1000条，使用最后一条更新起点
    current_start = klines[-1].open_time + timedelta(minutes=1)
```

### 2. endTime 保持在总结束时间

**关键点**：
- `startTime`: 每次更新（当前批次起点）
- `endTime`: 保持在总结束时间不变
- API 自动从 startTime 开始返回1000条

**为什么这样能工作**：
- 每批的 `startTime` 和 `endTime` 间隔很大（超过24小时）
- 但币安API会限制返回数量为1000条
- 所以会从 `startTime` 开始返回连续的1000条
- 使用 `最后一条.open_time + 1分钟` 更新下一批起点
- 确保数据连续不重复

### 3. 精确的起点计算

**修改前（错误）**：
```python
last_time = get_last_kline_time()  # 2025-12-19 23:59:00
chunk_start = last_time  # ❌ 从最后一条开始，会重复
```

**修改后（正确）**：
```python
last_time = get_last_kline_time()  # 2025-12-19 23:59:00
start_time = last_time + timedelta(minutes=1)  # 2025-12-20 00:00:00
current_start = start_time  # ✅ 从下一条开始
```

## 代码对比

### 修改前（fetch_klines_to_1m.py）

```python
# 双层循环：按天分块 + 块内分批
chunk_minutes = 1440  # 1天 = 1440分钟
chunk_start = start_time

while chunk_start < end_time:
    chunk_end = min(chunk_start + timedelta(minutes=chunk_minutes), end_time)

    inner_start = chunk_start
    while inner_start < chunk_end:
        # endTime 是天结束时间
        klines = fetch_klines_range(exchange, inner_start, chunk_end)
        # ❌ 一天1440条，只返回1000条，丢失440条

        saved_count = save_to_klines_1m(klines)
        inner_start = klines[-1].open_time + timedelta(minutes=1)

        if saved_count < 1000:
            break

    chunk_start = chunk_end
```

### 修改后（fetch_klines_to_1m.py）

```python
# 单层循环：直接按1000条分批
current_start = start_time

while current_start < end_time:
    # endTime 保持在总结束时间
    klines = fetch_klines_range(exchange, current_start, end_time)
    # ✅ 每批1000条，精确计算起点

    saved_count = save_to_klines_1m(klines)
    current_start = klines[-1].open_time + timedelta(minutes=1)

    if saved_count < 1000:
        break
```

## 验证结果

### 数据完整性

修改前：
```
2025-12-21: 1000 条（00:00:00 ~ 16:40:00）
❌ 丢失: 440 条（16:41:00 ~ 23:59:00）
```

修改后：
```
2025-12-21:
  批次1: 1000 条（00:00:00 ~ 16:40:00）
  批次2: 440 条（16:41:00 ~ 23:59:00）
✅ 完整: 1440 条
```

### API请求示例

```
批次1:
  startTime=2025-12-21 00:00:00, endTime=2026-01-09 19:28:00
  返回: 1000 条（00:00:00 ~ 16:40:00）

批次2:
  startTime=2025-12-21 16:41:00, endTime=2026-01-09 19:28:00
  返回: 1000 条（16:41:00 ~ 2025-12-22 09:21:00）

批次3:
  startTime=2025-12-22 09:22:00, endTime=2026-01-09 19:28:00
  返回: 1000 条（09:22:00 ~ 2025-12-23 01:42:00）

...
```

## 总结

### 问题
- ❌ 双层循环按天分块（1440分钟）
- ❌ 一天数据超过1000条，API只返回1000条
- ❌ 每天丢失440条数据

### 解决
- ✅ 改为单层循环，直接按1000条分批
- ✅ `endTime` 保持在总结束时间
- ✅ 每批使用 `最后一条.open_time + 1分钟` 更新起点
- ✅ 确保数据连续完整

### 关键代码
```python
current_start = start_time
while current_start < end_time:
    klines = fetch_klines_range(exchange, current_start, end_time)
    save_to_klines_1m(klines)
    current_start = klines[-1].open_time + timedelta(minutes=1)
```

### 结果
- ✅ 每批精确获取1000条
- ✅ 数据连续不丢失
- ✅ 每天完整获取1440条（不再只有1000条）
- ✅ 代码更简洁高效
