# 回测开始日期说明

## 日期
2026-01-07

## 用户问题

"为什么回测的数据第一条是2024年1月2日 0点？"

## 问题分析

### 配置的回测时间范围

**文件**: [core/config.py:71-72](core/config.py#L71-L72)

```python
REPLAY_START = '2024-01-01 00:00:00'  # 回测开始时间
REPLAY_END = '2024-01-10 23:59:59'    # 回测结束时间
```

### 数据库实际情况

```bash
# 查询2024-01-01的数据
SELECT COUNT(*) FROM klines_1m_macd_smooth_ma
WHERE open_time >= '2024-01-01' AND open_time < '2024-01-02';
-- 结果: 1440条 (完整的一天)

# 查询第一条数据
SELECT open_time FROM klines_1m_macd_smooth_ma
WHERE open_time >= '2024-01-01'
ORDER BY open_time ASC LIMIT 1;
-- 结果: 2024-01-01 00:00:00+00:00
```

### 结论

**数据库中有2024-01-01的完整数据，回测应该从2024-01-01 00:00:00开始！**

---

## 为什么看到2024-01-02？

### 可能原因1: 前端K线图显示

前端默认加载**最新100条K线**，而不是从回测开始时间加载。

**代码位置**: [web/templates/monitor.html:234](web/templates/monitor.html#L234)

```javascript
// loadKlines(100);  // 注释掉,避免加载错误的K线
```

当你点击"启动"后，回测从2024-01-01开始，但K线图显示的是最近的100条数据，可能不包含2024-01-01。

### 可能原因2: 日志输出

回测日志会输出第一条K线数据：

**代码位置**: [web_app.py:1327](web_app.py#L1327)

```python
logger.info("开始回测 - 数据回放模式")
logger.info(klines[0])  # 输出第一条K线
```

这条日志应该显示 `2024-01-01 00:00:00`，如果显示的是 `2024-01-02 00:00:00`，说明：
- 数据查询时被过滤了
- 或者时间范围配置有问题

---

## 如何验证

### 方法1: 查看日志

运行回测后，查看日志输出的第一条K线：

```bash
grep "开始回测" /tmp/web_app.log -A 2
```

**预期输出**:
```log
开始回测 - 数据回放模式
{'open_time': '2024-01-01 00:00:00+00:00', 'close': 43250.0, ...}
```

### 方法2: 查看sim_log表

```bash
sqlite3 data/klines.db "SELECT MIN(log_time), MAX(log_time), COUNT(*) FROM sim_log;"
```

应该能看到：
- MIN(log_time): 2024-01-01 ...
- MAX(log_time): 2024-01-10 ...
- COUNT(*): 实际处理的K线数量

### 方法3: 前端查看完整时间范围

在监控页面，输入完整的时间范围加载K线：

```
开始时间: 2024-01-01 00:00:00
结束时间: 2024-01-10 23:59:59
```

点击"查询"按钮，应该能看到从2024-01-01开始的完整K线图。

---

## 如果确实从2024-01-02开始

如果确认回测真的从2024-01-02开始，可能的原因：

### 1. 时间格式问题

检查`REPLAY_START`的格式：

```python
# 正确格式
REPLAY_START = '2024-01-01 00:00:00'  # ✓

# 或
REPLAY_START = '2024-01-01T00:00:00'  # ✓
```

### 2. 数据库查询问题

检查`DbKlineReader.get_klines_by_time_range()`的查询逻辑：

```python
# 文件: data_module/db_kline_reader.py:155
cursor.execute(query, (start_time_normalized, end_time_normalized))
```

查询使用 `>=` 开始时间，应该包含2024-01-01 00:00:00。

### 3. 预热期逻辑

检查是否有预热期逻辑跳过了第一天：

```python
# 预热期天数
REPLAY_WARM_DAYS = 200
```

预热期用于计算指标（如1天MACD），但**不应该跳过交易K线**。

---

## 解决方案

### 确保从2024-01-01开始

1. **检查配置**:
   ```bash
   # 确认环境变量
   echo $REPLAY_START
   # 应该输出: 2024-01-01 00:00:00
   ```

2. **检查日志**:
   ```bash
   # 查看回测开始时的日志
   grep "获取K线数据" /tmp/web_app.log
   # 应该看到: 获取K线数据: 2024-01-01 00:00:00 至 2024-01-10 23:59:59
   ```

3. **添加调试日志**:

   在 [web_app.py:1328](web_app.py#L1328) 添加：

   ```python
   for i, kline in enumerate(klines):
       # 输出前10条K线的时间
       if i < 10:
           logger.info(f"K线 #{i}: {kline.get('open_time')}")
   ```

---

## 总结

### 预期行为

- ✅ 回测应该从 `2024-01-01 00:00:00` 开始
- ✅ 数据库有完整的2024-01-01数据
- ✅ 第一条日志应该显示 `2024-01-01 00:00:00`

### 如果不是这样

- ❌ 检查 `REPLAY_START` 环境变量
- ❌ 检查数据库查询逻辑
- ❌ 检查是否有过滤逻辑跳过了第一天

### 调试建议

1. 查看完整日志
2. 验证数据库数据
3. 添加调试输出

---

## 相关文件

- **配置文件**: [core/config.py:71-72](core/config.py#L71-L72)
- **回测逻辑**: [web_app.py:1235-1450](web_app.py#L1235-L1450)
- **数据读取**: [data_module/db_kline_reader.py:115-164](data_module/db_kline_reader.py#L115-L164)

---

**建议**: 运行一次回测并检查日志，确认第一条K线的时间是否为 `2024-01-01 00:00:00`。
