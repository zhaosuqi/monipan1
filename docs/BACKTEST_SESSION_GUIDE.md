# 回测会话管理系统使用指南

## 概述

回测会话管理系统允许按时间阶段划分K线数据,进行分阶段的回测分析。每个会话独立统计,便于:

1. **按日/周/月分析** - 查看不同时间段的交易表现
2. **断点续传** - 每个会话独立运行,可随时停止和继续
3. **对比分析** - 比较不同时间段的策略表现
4. **详细统计** - 每个会话独立的盈亏、信号数统计

## 核心组件

### 1. BacktestSession (会话对象)

```python
@dataclass
class BacktestSession:
    session_id: str              # 会话ID
    start_time: pd.Timestamp      # 开始时间
    end_time: pd.Timestamp        # 结束时间
    klines: List[Dict]           # K线数据

    # 会话统计
    signals_detected: int         # 检测到的信号数
    positions_opened: int         # 开仓次数
    trades_completed: int         # 完成的交易数

    # 资金状态
    initial_capital: float        # 初始资金
    final_capital: float          # 最终资金
    pnl: float                    # 盈亏

    # 会话状态
    status: str                   # pending/running/completed/failed
```

### 2. BacktestSessionManager (会话管理器)

提供多种会话划分方法:

- `split_by_day()` - 按天划分
- `split_by_week()` - 按周划分
- `split_by_month()` - 按月划分
- `split_by_custom()` - 自定义时间间隔划分

## 使用方法

### 方法1: 通过Web API

```javascript
// 启动按天划分的会话回测
fetch('/api/backtest/session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        split_mode: 'day'  // day/week/month/custom
    })
})
.then(res => res.json())
.then(data => console.log(data));
```

### 方法2: 通过Python脚本

```python
from data_module.db_kline_reader import DbKlineReader
from signal_module.signal_calculator import SignalCalculator
from trade_module import TradeEngine, BacktestSessionManager
from core.config import config

# 1. 初始化
session_manager = BacktestSessionManager()
trade_engine = TradeEngine()
signal_calculator = SignalCalculator()

# 2. 读取K线数据
reader = DbKlineReader(
    db_path=config.HIST_DB_PATH,
    table_name='klines_1m_macd_smooth_ma'
)

klines = reader.get_klines_by_time_range(
    start_time=config.REPLAY_START,
    end_time=config.REPLAY_END
)

# 3. 划分会话(按天)
sessions = session_manager.split_by_day(klines)

# 4. 运行所有会话
results = session_manager.run_all_sessions(
    sessions=sessions,
    trade_engine=trade_engine,
    signal_calculator=signal_calculator
)

# 5. 查看结果
session_manager.print_session_summary(sessions)
trade_engine.print_summary()
```

### 方法3: 单日回测

```python
# 只回测特定日期
run_single_session_by_day('2024-01-01')
```

### 方法4: 多日对比

```python
# 对比多天的回测结果
compare_sessions_by_day([
    '2024-01-01',
    '2024-01-02',
    '2024-01-03'
])
```

## 会话划分模式

### 1. 按天划分 (split_mode='day')

每天一个独立会话,适合:
- 查看每日盈亏
- 分析日内交易表现
- 识别特定日期的异常

**示例:**
```
会话ID: day_20240101
时间: 2024-01-01 00:00:00 ~ 2024-01-01 23:59:59
K线: 1440条
盈亏: 0.001234 BTC
```

### 2. 按周划分 (split_mode='week')

每周一个独立会话,适合:
- 分析周度趋势
- 评估周间表现差异

**示例:**
```
会话ID: week_20240101
时间: 2024-01-01 00:00:00 ~ 2024-01-07 23:59:59
K线: 10080条
盈亏: 0.005678 BTC
```

### 3. 按月划分 (split_mode='month')

每月一个独立会话,适合:
- 月度绩效分析
- 长期趋势观察

**示例:**
```
会话ID: month_202401
时间: 2024-01-01 00:00:00 ~ 2024-01-31 23:59:59
K线: 44640条
盈亏: 0.023456 BTC
```

### 4. 自定义间隔 (split_mode='custom')

自定义小时间隔,适合:
- 测试特定时间窗口
- 分析特定时段表现

**示例:**
```python
# 配置间隔(需要在config中添加)
SESSION_INTERVAL_HOURS = 12

# 使用12小时间隔划分
sessions = session_manager.split_by_custom(klines, interval_hours=12)
```

## 会话统计输出

### 单会话输出

```
================================================================================
开始会话: day_20240101
时间范围: 2024-01-01 00:00:00 ~ 2024-01-01 23:59:59
K线数量: 1440
================================================================================
  会话 day_20240101 | 已处理 100/1440 | 信号: 3多/2空 | 资金: 1.001234 BTC
  ...

✓ 会话 day_20240101 完成
  盈亏: 0.001234 BTC
  信号: 5个
  当前资金: 1.001234 BTC
================================================================================
```

### 会话摘要

```
================================================================================
会话统计摘要
================================================================================
● day_20240101 | 2024-01-01 00:00 ~ 2024-01-01 23:59 | K线: 1440条 | 信号: 5个 | 盈亏: 0.001234 BTC | 状态: completed
● day_20240102 | 2024-01-02 00:00 ~ 2024-01-02 23:59 | K线: 1440条 | 信号: 3个 | 盈亏: -0.000567 BTC | 状态: completed
○ day_20240103 | 2024-01-03 00:00 ~ 2024-01-03 23:59 | K线: 1440条 | 信号: 0个 | 盈亏: 0.000000 BTC | 状态: pending
================================================================================
```

### 总体统计

```
================================================================================
回测统计摘要
================================================================================
总交易次数: 25
盈利次数: 15
亏损次数: 10
胜率: 60.00%
总盈亏: $1250.00 (0.029070 BTC)
初始资金: 1.000000 BTC
最终资金: 1.029070 BTC
收益率: 2.91%
平均盈利: $150.00
平均亏损: -$100.00
盈亏比: 2.25
检测信号: 50
实际开仓: 25
================================================================================
```

## WebSocket事件

### session_progress

会话进度更新事件:

```javascript
socket.on('session_progress', (data) => {
    console.log(`会话 ${data.session_id} 进度:`);
    console.log(`  已处理: ${data.processed}/${data.total}`);
    console.log(`  信号: ${data.buy_signals}多/${data.sell_signals}空`);
    console.log(`  当前资金: ${data.current_capital} BTC`);
});
```

### backtest_complete

回测完成事件:

```javascript
socket.on('backtest_complete', (data) => {
    console.log('回测完成!');
    console.log(`  划分模式: ${data.split_mode}`);
    console.log(`  会话总数: ${data.total_sessions}`);
    console.log(`  完成会话: ${data.completed_sessions}`);
    console.log(`  总交易: ${data.total_trades}`);
    console.log(`  总盈亏: $${data.total_pnl_usd}`);
    console.log(`  收益率: ${data.return_pct}%`);
    console.log(`  会话详情:`, data.sessions);
});
```

## 配置参数

在`core/config.py`中添加:

```python
# 会话模式配置
SESSION_INTERVAL_HOURS = 24  # 自定义模式下的时间间隔(小时)
```

## 最佳实践

1. **从小到大测试** - 先单日测试,再扩展到周/月
2. **记录会话ID** - 便于后续查询和分析
3. **定期保存日志** - 交易日志自动保存到sim_log表
4. **监控资金变化** - 关注每个会话的资金曲线
5. **对比分析** - 使用多日对比功能发现规律

## 故障排查

### 问题1: 会话数量为0

**原因:** K线数据为空或时间范围配置错误

**解决:**
- 检查`REPLAY_START`和`REPLAY_END`配置
- 确认数据库中有对应时间段的数据
- 使用`DbKlineReader`先测试数据读取

### 问题2: 会话运行中断

**原因:** 程序异常或用户手动停止

**解决:**
- 查看日志找出中断原因
- 修复后可重新运行(已完成会话会被标记为completed)
- 使用单会话模式逐步测试

### 问题3: 统计数据不准确

**原因:** 交易引擎状态未重置

**解决:**
- 每次运行前创建新的`TradeEngine`实例
- 或调用`trade_engine`的reset方法(如果实现)

## 示例脚本

完整示例请参考: `examples/backtest_with_sessions.py`

包含:
- 按天回测
- 按周回测
- 按月回测
- 单日回测
- 多日对比
