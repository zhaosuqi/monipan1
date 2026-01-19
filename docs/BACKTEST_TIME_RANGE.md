# K线时间范围自动匹配功能

## 问题描述

**用户反馈**: 回测时间是2024年1月,但K线显示的还是2023年的数据。

**根本原因**:
1. 前端`loadKlines()`只加载最新的N条K线,不考虑回测时间范围
2. 后端`/api/klines`接口不支持时间范围参数
3. 启动回测时没有将时间范围信息发送给前端

## 解决方案

### 1. 后端修改

#### 修改 `/api/klines` 接口支持时间范围查询

**文件**: [web_app.py:413-456](web_app.py#L413-L456)

**新增参数**:
- `start_time` (可选): 开始时间
- `end_time` (可选): 结束时间
- `limit` (可选): 默认100条

**查询逻辑**:
```python
# 如果指定了完整时间范围
if start_time and end_time:
    klines = reader.get_klines_by_time_range(
        start_time=start_time,
        end_time=end_time
    )

# 如果只有开始时间
elif start_time:
    klines = reader.get_klines_by_time_range(
        start_time=start_time,
        end_time=None
    )
    # 限制数量
    if len(klines) > limit:
        klines = klines[:limit]

# 默认: 获取最新的N条
else:
    klines = reader.get_klines(limit=limit)
```

#### 修改启动API返回回测时间范围

**文件**: [web_app.py:332-341](web_app.py#L332-L341)

**修改内容**:
```python
# 添加回测时间范围信息
bot_state['backtest_start'] = config.REPLAY_START
bot_state['backtest_end'] = config.REPLAY_END

logger.info(f"回测时间范围: {config.REPLAY_START} ~ {config.REPLAY_END}")
```

**返回数据格式**:
```json
{
  "success": true,
  "message": "机器人已启动 - 数据库回测模式",
  "data": {
    "running": true,
    "mode": "backtest",
    "backtest_start": "2024-01-01 00:00:00",
    "backtest_end": "2024-01-10 23:59:59",
    ...
  }
}
```

### 2. 前端修改

#### 新增按时间范围加载K线函数

**文件**: [web/templates/monitor.html:458-480](web/templates/monitor.html#L458-L480)

**新增函数**:
```javascript
function loadKlinesByTimeRange(startTime, endTime) {
    const params = new URLSearchParams({
        start_time: startTime,
        end_time: endTime
    });

    fetch(`/api/klines?${params}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                updateChart(data.data);
                showToast(`已加载回测时间段K线: ${data.data.length} 条`, 'success');
            }
        });
}
```

#### 启动时自动加载回测时间范围的K线

**文件**: [web/templates/monitor.html:692-696](web/templates/monitor.html#L692-L696)

**修改内容**:
```javascript
// 如果是回测模式且有回测时间范围,加载对应时间范围的K线
if (data.data.mode === 'backtest' &&
    data.data.backtest_start &&
    data.data.backtest_end) {
    console.log(`加载回测时间范围K线: ${data.data.backtest_start} ~ ${data.data.backtest_end}`);
    loadKlinesByTimeRange(data.data.backtest_start, data.data.backtest_end);
}
```

## 工作流程

```
用户点击"启动"
  ↓
前端调用 POST /api/bot/start
  ↓
后端读取配置中的回测时间范围
  ↓
返回包含 backtest_start 和 backtest_end 的响应
  ↓
前端检测到回测模式和时间范围
  ↓
调用 loadKlinesByTimeRange(start, end)
  ↓
后端从数据库按时间范围查询K线
  ↓
返回指定时间范围的K线数据
  ↓
前端更新图表显示正确的K线
  ↓
图表显示回测时间段的K线 + 买卖点标记
```

## API接口

### GET /api/klines

获取K线数据接口,支持多种查询模式。

#### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| limit | int | 否 | 返回条数,默认100(仅在不指定时间范围时生效) |
| start_time | string | 否 | 开始时间,格式: '2024-01-01 00:00:00' |
| end_time | string | 否 | 结束时间,格式: '2024-01-10 23:59:59' |

#### 查询模式

**1. 默认模式** (获取最新N条)
```
GET /api/klines?limit=100
```

**2. 时间范围模式** (获取指定时间段的所有K线)
```
GET /api/klines?start_time=2024-01-01%2000:00:00&end_time=2024-01-10%2023:59:59
```

**3. 从某时间开始模式** (获取从某时间开始的N条K线)
```
GET /api/klines?start_time=2024-01-01%2000:00:00&limit=1000
```

#### 响应格式

```json
{
  "success": true,
  "message": "成功获取K线数据",
  "data": [
    {
      "time": "2024-01-01 00:00:00",
      "open": 42150.5,
      "high": 42280.3,
      "low": 42100.2,
      "close": 42250.8,
      "volume": 123.456
    },
    ...
  ]
}
```

## 配置说明

### core/config.py

回测时间范围配置:

```python
# 回测时间范围
self.REPLAY_START = '2024-01-01 00:00:00'
self.REPLAY_END = '2024-01-10 23:59:59'
```

### 修改回测时间

**方法1: 环境变量**
```bash
export REPLAY_START='2024-02-01 00:00:00'
export REPLAY_END='2024-02-10 23:59:59'
python web_app.py
```

**方法2: 修改配置文件**
直接修改 `core/config.py` 中的 `REPLAY_START` 和 `REPLAY_END`

**方法3: .env文件**
在项目根目录创建 `.env` 文件:
```
REPLAY_START=2024-02-01 00:00:00
REPLAY_END=2024-02-10 23:59:59
```

## 调试方法

### 1. 检查配置

```bash
# 查看当前回测时间范围配置
python3 -c "from core.config import config; print(f'Start: {config.REPLAY_START}, End: {config.REPLAY_END}')"
```

### 2. 测试API接口

```bash
# 测试时间范围查询
curl "http://localhost:8076/api/klines?start_time=2024-01-01%2000:00:00&end_time=2024-01-10%2023:59:59"
```

### 3. 浏览器控制台

启动回测后,在浏览器控制台应该看到:
```
解析响应数据: {success: true, data: {...}}
加载回测时间范围K线: 2024-01-01 00:00:00 ~ 2024-01-10 23:59:59
✓ 图表更新成功, 12960 条数据, 0 个标记
已加载回测时间段K线: 12960 条 (2024-01-01 00:00:00 ~ 2024-01-10 23:59:59)
```

### 4. 服务器日志

```bash
# 后端日志应该显示
获取K线数据请求, limit=None, start_time=2024-01-01 00:00:00, end_time=2024-01-10 23:59:59
从表 klines_1m_macd_smooth_ma 读取数据
按时间范围获取到 12960 条K线数据
回测机器人已启动 - 模式: 数据库回测模式
回测时间范围: 2024-01-01 00:00:00 ~ 2024-01-10 23:59:59
```

## 数据量说明

### 不同时间范围的数据量

| 时间范围 | 预计K线数量 | 说明 |
|---------|------------|------|
| 1天 | ~1440条 | 1分钟K线 |
| 10天 | ~14400条 | 1分钟K线 |
| 1个月 | ~43200条 | 1分钟K线 |
| 1季度 | ~129600条 | 1分钟K线 |

### 性能优化建议

1. **大批量数据** (>5万条):
   - 考虑使用采样显示
   - 或使用5分钟/15分钟K线

2. **前端渲染**:
   - Lightweight Charts可以流畅处理1-2万个数据点
   - 超过5万个可能需要分页或采样

3. **数据库查询**:
   - 确保时间字段有索引
   - 避免全表扫描

## 常见问题

### 问题1: K线时间还是不对

**检查**:
1. 配置文件中的时间是否正确
2. 数据库中是否有该时间段的数据
3. API响应的时间范围是否正确

**解决**:
```bash
# 查询数据库中实际的时间范围
sqlite3 data/hist_kline.db "SELECT MIN(open_time), MAX(open_time) FROM klines_1m_macd_smooth_ma"
```

### 问题2: 没有数据返回

**原因**:
- 数据库中没有该时间段的数据
- 时间格式不正确

**解决**:
```bash
# 检查表中是否有数据
sqlite3 data/hist_kline.db "SELECT COUNT(*) FROM klines_1m_macd_smooth_ma WHERE open_time >= '2024-01-01T00:00:00'"
```

### 问题3: 加载太慢

**原因**:
- 时间范围太大,数据量太多
- 数据库查询慢

**解决**:
- 缩短时间范围
- 添加数据库索引
- 使用数据采样

## 相关功能

- [TRADE_MARKERS.md](TRADE_MARKERS.md) - 买卖点标记功能
- [CHART_FIX.md](CHART_FIX.md) - K线图表初始化修复

## 总结

通过在启动时传递回测时间范围,并按时间范围加载K线数据,确保了K线图表显示的时间段与回测时间段一致。这使得:

1. ✅ K线时间与回测时间完全匹配
2. ✅ 买卖点标记显示在正确的时间位置
3. ✅ 用户可以直观地看到回测期间的价格走势
4. ✅ 支持灵活配置回测时间范围

修改完成后,K线图会自动显示回测时间段的正确数据!
