# 修复币安API时间范围限制问题

## 问题

日志显示需要补充23664条K线，但只补充了1000条就停止了：

```bash
需要补充约 23664 条K线
→ 批次 1: 从 2025-12-24 07:03:00 开始获取
✓ 批次 1 完成，本批获取 1000 条，累计获取 1000 条K线
# 然后显示"数据库已是最新"
```

## 根本原因

### 币安API的时间范围限制

根据币安API文档，K线接口的 `startTime` 和 `endTime` 参数有一个重要限制：

**如果 startTime 和 endTime 之间的间隔超过24小时，API会忽略这些参数，只返回最近的1000条K线！**

### 错误的代码

```python
# 错误：同时使用 startTime 和 endTime
klines = exchange.get_klines(
    symbol=symbol,
    interval=interval,
    limit=1000,
    start_time=start_time,  # 2025-12-24 07:03:00
    end_time=end_time       # 2026-01-09 17:27:00（间隔15天！）
)
```

**结果：**
- API忽略 startTime 和 endTime（因为间隔超过24小时）
- 返回最近的1000条K线（2026-01-09 00:00 ~ 17:27）
- 这些K线被保存后，`last_time` 更新为 2026-01-09 17:28:00
- 下次检查时发现已经是最新的，停止获取

### 错误的停止条件

```python
# 错误：基于保存的数量判断
if saved_count < 1000:
    break
```

**问题：**
- `saved_count` 是本地过滤后的数量
- 如果本地过滤（end_time）过滤掉了一些K线，`saved_count` 可能 < 1000
- 但这不意味着已经补完所有数据了

## 解决方案

### 修改1: 不使用 end_time 参数

**修改前：**
```python
klines = exchange.get_klines(
    symbol=symbol,
    interval=interval,
    limit=1000,
    start_time=start_time,
    end_time=end_time  # ❌ 删除这个参数
)
```

**修改后：**
```python
# 只使用 startTime，不使用 endTime
klines = exchange.get_klines(
    symbol=symbol,
    interval=interval,
    limit=1000,
    start_time=start_time
    # 不传递 end_time，避免24小时限制
)

# 然后在本地进行时间范围过滤
for kline in klines:
    if end_time is None or kline.close_time <= end_time:
        finished_klines.append(kline)
```

**优势：**
- API会从 startTime 开始返回最多1000条K线
- 本地过滤确保不超出 end_time
- 可以分批获取任意时间范围的数据

### 修改2: 返回API原始数量

**修改前：**
```python
def fetch_new_klines(...):
    # ...
    return finished_klines
```

**修改后：**
```python
def fetch_new_klines(...):
    # ...
    api_count = len(klines)  # API返回的原始数量

    # 本地过滤
    finished_klines = [...]

    return finished_klines, api_count
```

### 修改3: 基于API原始数量判断

**修改前：**
```python
# 错误：基于保存的数量
if saved_count < 1000:
    logger.info("本批获取数量 < 1000，说明已补完")
    break
```

**修改后：**
```python
# 正确：基于API返回的原始数量
if api_count < 1000:
    logger.info("API返回数量 < 1000，说明已补完")
    break

# 如果本地过滤后为空，检查API是否返回了数据
if not new_klines:
    if api_count == 0:
        logger.info("API未返回数据，停止获取")
        break
    else:
        logger.info(
            "API返回了数据，但都被本地过滤掉了，"
            "说明已补完所有数据"
        )
        break
```

## 修改后的流程

```python
# 1. 计算需要补充的时间范围
last_time = get_last_kline_time()  # 2025-12-24 07:03:00
end_time = 当前已完结时间            # 2026-01-09 17:27:00

# 2. 分批获取
batch_count = 0
while last_time < end_time:
    batch_count += 1

    # 获取K线（只使用start_time）
    new_klines, api_count = fetch_new_klines(
        exchange, last_time, end_time
    )

    # API会从 last_time 开始返回1000条
    # 本地过滤会移除超出 end_time 的K线

    # 保存
    saved_count = save_to_klines_1m(new_klines)

    # 更新：使用最后一条的 open_time + 1分钟
    last_time = new_klines[-1].open_time + timedelta(minutes=1)

    # 如果API返回数量 < 1000，说明已经补完
    if api_count < 1000:
        break

    # 避免请求过快
    time.sleep(0.5)
```

## 预期结果

```bash
需要补充约 23664 条K线

→ 批次 1: 从 2025-12-24 07:03:00 开始获取
API返回 1000 条K线，本地过滤后 1000 条已完结且符合时间范围
✓ 批次 1 完成，本批获取 1000 条，累计获取 1000 条K线

→ 批次 2: 从 2025-12-24 20:43:00 开始获取
API返回 1000 条K线，本地过滤后 1000 条已完结且符合时间范围
✓ 批次 2 完成，本批获取 1000 条，累计获取 2000 条K线

→ 批次 3: 从 2025-12-25 10:23:00 开始获取
API返回 1000 条K线，本地过滤后 1000 条已完结且符合时间范围
✓ 批次 3 完成，本批获取 1000 条，累计获取 3000 条K线

...

→ 批次 23: 从 2026-01-08 22:03:00 开始获取
API返回 1000 条K线，本地过滤后 1000 条已完结且符合时间范围
✓ 批次 23 完成，本批获取 1000 条，累计获取 23000 条K线

→ 批次 24: 从 2026-01-09 07:43:00 开始获取
API返回 664 条K线，本地过滤后 664 条已完结且符合时间范围
✓ 批次 24 完成，本批获取 664 条，累计获取 23664 条K线
API返回数量 664 < 1000，说明已补完所有数据
```

## 关键修改

### fetch_klines_to_1m.py

**1. fetch_new_klines() 函数（第66-126行）：**
- 不使用 `end_time` 参数调用API
- 返回元组：`(过滤后的K线, API原始数量)`
- 添加本地过滤逻辑

**2. get_last_kline_time() 函数（第26-63行）：**
- 返回 `open_time` 而不是 `close_time`

**3. 主循环（第328-384行）：**
- 使用 `api_count` 判断是否停止
- 检查本地过滤后为空的情况
- 使用 `open_time + 1分钟` 更新 `last_time`

## 总结

### 问题

- ❌ 同时使用 startTime 和 endTime，触发24小时限制
- ❌ API返回最近的1000条，而不是从指定时间开始
- ❌ 基于保存的数量判断停止，导致提前停止

### 解决

- ✅ 只使用 startTime，不使用 endTime
- ✅ 本地进行时间范围过滤
- ✅ 基于API返回的原始数量判断停止
- ✅ 使用 open_time 追踪进度

### 结果

现在可以正确地分批获取任意时间范围的数据了！

## 测试建议

1. **清空测试数据**
```bash
sqlite3 data/klines.db "DELETE FROM klines_1m WHERE date(open_time) > '2025-12-24'"
```

2. **重新运行**
```bash
./start_fetch_klines_to_1m.sh
```

3. **观察日志**
- 应该看到约24个批次
- 每批API返回1000条（最后一批可能少于1000）
- 累计数量应该达到23664条

4. **验证数据**
```bash
sqlite3 data/klines.db "SELECT COUNT(*) FROM klines_1m"
sqlite3 data/klines.db "SELECT MIN(open_time), MAX(open_time) FROM klines_1m"
```
