# 实时K线数据补充服务使用指南

## 功能概述

`fetch_realtime_klines.py` 是一个实时K线数据补充脚本，用于：

1. **自动补充K线数据** - 从币安API获取最新的分钟K线
2. **智能时间控制** - 只获取已完结的K线，不包含当前未完结的K线
3. **定时查询** - 每10秒查询一次，精确控制在01, 11, 21, 31, 41, 51秒执行
4. **自动计算指标** - 计算MACD、KDJ、MA等技术指标
5. **实时入库** - 将数据和指标写入 `klines_1m_macd_smooth_ma` 表

## 工作流程

```
┌─────────────────────────────────────────────────────────────┐
│  1. 读取 klines_1m 表最后一条K线时间                         │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  2. 等待查询时间点 (01, 11, 21, 31, 41, 51秒)                │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  3. 从币安API获取K线数据（已完结的）                          │
│     - 从最后时间开始                                          │
│     - 到上一分钟截止（确保已完结）                             │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  4. 计算技术指标                                              │
│     - MACD (12, 26, 9)                                       │
│     - KDJ                                                   │
│     - MA (5, 10, 20, 60...)                                  │
│     - 其他指标                                               │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  5. 写入 klines_1m_macd_smooth_ma 表                         │
│     - INSERT OR REPLACE 避免重复                              │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
                    返回步骤2
```

## 快速开始

### 1. 启动服务

```bash
./start_fetch_klines.sh
```

或者直接运行：

```bash
python fetch_realtime_klines.py
```

### 2. 查看日志

程序会输出详细日志：

```
============================================================
启动实时K线数据补充
============================================================
交易对: BTCUSD_PERP
交易所: 币安测试网
查询间隔: 每10秒（在01, 11, 21, 31, 41, 51秒执行）
============================================================
✓ 已连接到币安交易所
数据库最后K线时间: 2026-01-09 00:45:00

============================================================
第 1 次查询
============================================================
需要获取数据: 2026-01-09 00:45:00 ~ 2026-01-09 00:50:00
获取到 6 条K线
✓ 指标计算完成
✓ 保存完成: 插入 6 条，跳过 0 条
✓ 本批处理完成，累计获取 6 条K线
等待下次查询...
```

### 3. 停止服务

按 `Ctrl+C` 停止程序。

程序会输出统计信息：

```
============================================================
程序结束
总查询次数: 120
总获取K线: 120 条
============================================================
```

## 查询时间说明

程序精确控制在每分钟的以下秒数执行查询：

- **00分01秒** - 第1次查询
- **00分11秒** - 第2次查询
- **00分21秒** - 第3次查询
- **00分31秒** - 第4次查询
- **00分41秒** - 第5次查询
- **00分51秒** - 第6次查询
- **01分01秒** - 下一分钟...

**为什么选择这些时间点？**

1. **避开整点** - 避免在00秒时查询，那时K线可能未完结
2. **分散负载** - 分散在每分钟的不同时间点，避免API请求过于集中
3. **及时更新** - 最多等待10秒即可获取最新数据

## 数据完整性保证

### 1. 只获取已完结的K线

```python
# 例如现在是 10:00:45
end_time = 当前时间 - 1分钟 = 09:59:00

# 只查询到 09:59:00 的K线（已完结）
# 不包含 10:00:00 的K线（正在形成中）
```

### 2. 增量更新

```python
# 从数据库最后时间开始
last_time = klines_1m最后一条时间

# 获取 last_time ~ end_time 之间的K线
new_klines = fetch_from_binance(last_time, end_time)
```

### 3. 幂等性保证

使用 `INSERT OR REPLACE` 确保重复执行不会产生重复数据。

```sql
INSERT OR REPLACE INTO klines_1m_macd_smooth_ma
```

## 配置说明

### 环境变量（.env文件）

```bash
# 币安API配置
BINANCE_API_KEY=你的API密钥
BINANCE_API_SECRET=你的API密钥
BINANCE_TESTNET=1  # 1=测试网, 0=实盘

# 交易对
SYMBOL=BTCUSD_PERP

# 数据库路径
DB_PATH=data/klines.db
```

### 修改查询间隔

如需修改查询时间点，编辑 `fetch_realtime_klines.py` 中的 `wait_for_next_query_time()` 函数：

```python
def wait_for_next_query_time():
    # 修改这里的时间点
    if current_second < 5:
        next_second = 5
    elif current_second < 15:
        next_second = 15
    # ...
```

## 数据库表结构

### klines_1m 表（原始数据）

```sql
CREATE TABLE klines_1m (
    open_time TEXT PRIMARY KEY,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    close_time TEXT,
    ...
);
```

### klines_1m_macd_smooth_ma 表（含指标）

包含所有原始列 + 技术指标列：

- **MACD**: `macd12m`, `dif12m`, `dea12m`, `bar12m`
- **KDJ**: `k_15`, `d_15`, `j_15`
- **MA**: `ma5`, `ma10`, `ma20`, `ma60`...
- **其他**: `hist15m`, `dif15m`, `dea15m`...

## 故障排查

### 问题1: 未获取到新K线

**检查：**
- 数据库时间是否已最新
- 网络连接是否正常
- API密钥是否正确

**解决：**
```bash
# 查看当前最后时间
sqlite3 data/klines.db "SELECT close_time FROM klines_1m ORDER BY close_time DESC LIMIT 1"

# 查看当前时间
date
```

### 问题2: 指标计算失败

**原因：** 历史数据不足，无法计算某些指标

**解决：**
- 确保有至少200天的历史数据（用于计算长期MA）
- 查看日志中的错误信息

### 问题3: 程序运行一段时间后停止

**可能原因：**
- API限流
- 网络中断
- 程序异常

**解决：**
```bash
# 使用systemd或supervisor守护进程运行
# 添加自动重启机制
```

## 性能优化

### 1. 批量写入

程序将多条K线打包写入数据库，减少I/O操作：

```python
# 批量插入多条
save_to_database(klines_with_indicators)
```

### 2. 增量计算

只计算新增K线的指标，避免重复计算：

```python
# 获取最后时间后，只获取新数据
new_klines = fetch_new_klines(exchange, last_time)
```

### 3. WAL模式

使用SQLite的WAL模式提高并发性能：

```python
conn.execute("PRAGMA journal_mode=WAL")
```

## 监控建议

### 1. 日志监控

```bash
# 查看实时日志
tail -f logs/fetch_realtime.log

# 只看错误
tail -f logs/fetch_realtime.log | grep ERROR
```

### 2. 数据库监控

```bash
# 查看最新数据时间
sqlite3 data/klines.db \
  "SELECT close_time FROM klines_1m_macd_smooth_ma \
   ORDER BY close_time DESC LIMIT 1"

# 查看数据条数
sqlite3 data/klines.db \
  "SELECT COUNT(*) FROM klines_1m_macd_smooth_ma"
```

### 3. API调用监控

程序日志会记录每次查询：

```
第 10 次查询
获取到 1 条K线
```

如果长时间没有获取到新K线，检查：
- 网络连接
- API限流状态
- 交易对是否正确

## 与主程序配合

### 方案1: 独立运行

```bash
# 终端1: 启动数据补充
./start_fetch_klines.sh

# 终端2: 启动Web监控
./start_web_monitor.sh
```

### 方案2: 后台运行

```bash
# 后台运行数据补充
nohup ./start_fetch_klines.sh > logs/fetch_realtime.log 2>&1 &

# 查看进程
ps aux | grep fetch_realtime

# 停止
pkill -f fetch_realtime
```

### 方案3: 使用systemd

创建 `/etc/systemd/system/fetch-klines.service`:

```ini
[Unit]
Description=Realtime Kline Data Fetcher
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/monipan
ExecStart=/path/to/monipan/start_fetch_klines.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable fetch-klines
sudo systemctl start fetch-klines
sudo systemctl status fetch-klines
```

## 注意事项

1. **API限流**
   - 币安API有请求频率限制
   - 当前每10秒一次，在限制范围内
   - 不要减少查询间隔

2. **数据一致性**
   - 确保时区正确
   - 使用UTC时间
   - 避免重复数据

3. **网络稳定性**
   - 使用可靠的网络环境
   - 考虑添加重试机制
   - 监控API调用成功率

4. **资源占用**
   - 内存占用较小（~100MB）
   - CPU占用很低
   - 主要为数据库写入I/O

## 常见问题

### Q: 为什么不在00秒查询？

A: 00秒时K线可能还未完全形成，等待几十秒确保数据已完结。

### Q: 为什么不用WebSocket？

A: WebSocket推送的是实时数据，包含未完结的K线。本脚本需要的是已确认完结的K线数据。

### Q: 能否修改为每5秒查询？

A: 不建议。币安API有频率限制，每10秒已经足够实时。

### Q: 数据会重复吗？

A: 不会。使用 `INSERT OR REPLACE` 确保幂等性。

## 相关文件

- `fetch_realtime_klines.py` - 主程序
- `start_fetch_klines.sh` - 启动脚本
- `indicator_module/indicator_calculator.py` - 指标计算
- `exchange_layer/binance_exchange.py` - 交易所接口

## 技术支持

如有问题：
1. 查看程序日志输出
2. 检查数据库表数据
3. 验证API连接状态
4. 确认环境变量配置
