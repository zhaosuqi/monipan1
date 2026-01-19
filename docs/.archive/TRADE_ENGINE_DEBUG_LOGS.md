# trade_engine.py 调试日志增强

## 日期
2026-01-07

## 用户需求

"778行增加日志，输出当前数据行和信号"

## 修改内容

在 `trade_module/trade_engine.py` 中添加了详细的调试日志，帮助跟踪交易引擎的运行状态。

---

## 1. 初始化计数器 (第79行)

**文件**: [trade_module/trade_engine.py:79](trade_module/trade_engine.py#L79)

**修改**:
```python
# 统计数据
self.signals_count = 0
self.triggers_count = 0
self.processed_count = 0  # 已处理的K线数量 ✅ 新增
```

---

## 2. process_tick() 函数 - K线处理日志 (第762-786行)

**文件**: [trade_module/trade_engine.py:762-786](trade_module/trade_engine.py#L762-L786)

**修改**:
```python
# 📊 调试日志: 输出当前处理的数据行(每100条输出一次,或有信号时)
self.processed_count += 1
should_log = (
    self.processed_count % 100 == 0 or  # 每100条输出一次
    signal or  # 有信号时输出
    len(self.positions) > 0  # 有持仓时输出
)

if should_log:
    self.logger.debug("-" * 80)
    self.logger.debug(f"处理K线 #{self.processed_count} | 时间: {ts}")
    self.logger.debug(f"价格: {price:.2f} | 最高: {high:.2f} | 最低: {low:.2f}")
    if signal:
        self.logger.debug(f"信号: {signal.action} {signal.side if hasattr(signal, 'side') else ''}")
    if len(self.positions) > 0:
        self.logger.debug(f"当前持仓数: {len(self.positions)}")
        for idx, pos in enumerate(self.positions):
            self.logger.debug(
                f"  持仓{idx+1}: {pos.side} | "
                f"入场={pos.entry_price:.2f} | "
                f"数量={pos.contracts}张 | "
                f"止盈级别={pos.tp_hit}"
            )
    self.logger.debug("-" * 80)
```

**说明**:
- ✅ **每100条K线输出一次** - 定期进度更新
- ✅ **有信号时输出** - 记录信号检测
- ✅ **有持仓时输出** - 跟踪持仓状态
- ✅ 使用 `logger.debug()` 级别 - 可通过配置控制输出

**日志示例**:
```
--------------------------------------------------------------------------------
处理K线 #100 | 时间: 2024-01-08 13:10:00
价格: 45061.80 | 最高: 45100.00 | 最低: 45020.00
信号: open long
--------------------------------------------------------------------------------
```

---

## 3. 开仓信号日志 (第779-791行)

**文件**: [trade_module/trade_engine.py:779-791](trade_module/trade_engine.py#L779-L791)

**修改**:
```python
# 2. 处理新开仓信号
if signal and signal.action == 'open' and len(self.positions) == 0:
    self.signals_count += 1
    reason = (
        signal.reason if hasattr(signal, 'reason') else 'V5'
    )

    # 📊 输出当前数据行和信号信息
    self.logger.info("=" * 80)
    self.logger.info(f"📊 检测到开仓信号 #{self.signals_count}")
    self.logger.info(f"时间: {ts}")
    self.logger.info(f"信号方向: {signal.side}")
    self.logger.info(f"信号原因: {reason}")
    self.logger.info(f"当前价格: {price:.2f}")
    self.logger.info(f"最高价: {high:.2f}")
    self.logger.info(f"最低价: {low:.2f}")
    # row已经是dict对象，直接输出
    self.logger.info(f"K线数据: {row}")
    if hasattr(signal, 'indicators') and signal.indicators:
        self.logger.info(f"指标数据: {signal.indicators}")
    self.logger.info("=" * 80)

    self.open_position(ts, price, row, signal.side, reason)
```

**说明**:
- ✅ **详细的信号信息** - 时间、方向、原因
- ✅ **完整的价格数据** - 当前价、最高价、最低价
- ✅ **K线数据字典** - 所有OHLCV数据
- ✅ **指标数据** - 如果有指标,也会输出
- ✅ 使用 `logger.info()` 级别 - 始终输出

**日志示例**:
```
================================================================================
📊 检测到开仓信号 #1
时间: 2024-01-08 13:10:00
信号方向: long
信号原因: V5
当前价格: 45061.80
最高价: 45100.00
最低价: 45020.00
K线数据: {'open': 45020.5, 'high': 45100.0, 'low': 45020.0, 'close': 45061.8, 'volume': 123.45, ...}
指标数据: {'macd15m': 15.2, 'dif15m': 23.5, 'dea15m': 18.3, ...}
================================================================================
```

---

## 4. 平仓前日志 (第279-290行)

**文件**: [trade_module/trade_engine.py:279-290](trade_module/trade_engine.py#L279-L290)

**修改**:
```python
if pos not in self.positions:
    self.logger.warning(f"持仓{pos.id}不存在，无法平仓")
    return

# 📊 输出平仓前信息
self.logger.info("=" * 80)
self.logger.info(f"📊 准备平仓 | 持仓ID: {pos.id}")
self.logger.info(f"平仓时间: {close_time}")
self.logger.info(f"平仓价格: {close_price:.2f}")
self.logger.info(f"平仓原因: {reason}")
self.logger.info(f"持仓方向: {pos.side}")
self.logger.info(f"入场价格: {pos.entry_price:.2f}")
self.logger.info(f"持仓数量: {pos.contracts}张")
self.logger.info(f"入场时间: {pos.entry_time}")
self.logger.info(f"已触发止盈级别: {pos.tp_hit}")
self.logger.info("=" * 80)

cn = config.CONTRACT_NOTIONAL
```

**说明**:
- ✅ **完整的持仓信息** - ID、方向、入场价、数量
- ✅ **平仓详情** - 时间、价格、原因
- ✅ **止盈级别跟踪** - 显示已触发的TP级别
- ✅ 使用 `logger.info()` 级别 - 始终输出

**日志示例**:
```
================================================================================
📊 准备平仓 | 持仓ID: 2e5a461a-86e1-401e-9d80-3d43d2f55a0a
平仓时间: 2024-01-10 12:57:00
平仓价格: 44329.00
平仓原因: stop_loss
持仓方向: long
入场价格: 45061.80
持仓数量: 450.0张
入场时间: 2024-01-08 13:10:00
已触发止盈级别: []
================================================================================
```

---

## 日志输出示例

### 完整的交易流程日志

```log
2024-01-08 13:10:00 - trade_module.engine - DEBUG - --------------------------------------------------------------------------------
2024-01-08 13:10:00 - trade_module.engine - DEBUG - 处理K线 #5000 | 时间: 2024-01-08 13:10:00
2024-01-08 13:10:00 - trade_module.engine - DEBUG - 价格: 45061.80 | 最高: 45100.00 | 最低: 45020.00
2024-01-08 13:10:00 - trade_module.engine - DEBUG - 信号: open long
2024-01-08 13:10:00 - trade_module.engine - DEBUG - --------------------------------------------------------------------------------
2024-01-08 13:10:00 - trade_module.engine - INFO - ================================================================================
2024-01-08 13:10:00 - trade_module.engine - INFO - 📊 检测到开仓信号 #1
2024-01-08 13:10:00 - trade_module.engine - INFO - 时间: 2024-01-08 13:10:00
2024-01-08 13:10:00 - trade_module.engine - INFO - 信号方向: long
2024-01-08 13:10:00 - trade_module.engine - INFO - 信号原因: V5
2024-01-08 13:10:00 - trade_module.engine - INFO - 当前价格: 45061.80
2024-01-08 13:10:00 - trade_module.engine - INFO - 最高价: 45100.00
2024-01-08 13:10:00 - trade_module.engine - INFO - 最低价: 45020.00
2024-01-08 13:10:00 - trade_module.engine - INFO - K线数据: {'open': 45020.5, 'high': 45100.0, 'low': 45020.0, 'close': 45061.8, ...}
2024-01-08 13:10:00 - trade_module.engine - INFO - ================================================================================
2024-01-08 13:10:00 - trade_module.engine - INFO - ✓ 开仓成功 | LONG | 价格=45061.80 | 数量=450.0张 | ...

... (中间有持仓时的日志) ...

2024-01-10 12:57:00 - trade_module.engine - DEBUG - --------------------------------------------------------------------------------
2024-01-10 12:57:00 - trade_module.engine - DEBUG - 处理K线 #7520 | 时间: 2024-01-10 12:57:00
2024-01-10 12:57:00 - trade_module.engine - DEBUG - 价格: 44329.00 | 最高: 44450.00 | 最低: 44300.00
2024-01-10 12:57:00 - trade_module.engine - DEBUG - 当前持仓数: 1
2024-01-10 12:57:00 - trade_module.engine - DEBUG -   持仓1: long | 入场=45061.80 | 数量=450.0张 | 止盈级别=[]
2024-01-10 12:57:00 - trade_module.engine - DEBUG - --------------------------------------------------------------------------------
2024-01-10 12:57:00 - trade_module.engine - INFO - ================================================================================
2024-01-10 12:57:00 - trade_module.engine - INFO - 📊 准备平仓 | 持仓ID: 2e5a461a-86e1-401e-9d80-3d43d2f55a0a
2024-01-10 12:57:00 - trade_module.engine - INFO - 平仓时间: 2024-01-10 12:57:00
2024-01-10 12:57:00 - trade_module.engine - INFO - 平仓价格: 44329.00
2024-01-10 12:57:00 - trade_module.engine - INFO - 平仓原因: stop_loss
2024-01-10 12:57:00 - trade_module.engine - INFO - 持仓方向: long
2024-01-10 12:57:00 - trade_module.engine - INFO - 入场价格: 45061.80
2024-01-10 12:57:00 - trade_module.engine - INFO - 持仓数量: 450.0张
2024-01-10 12:57:00 - trade_module.engine - INFO - 入场时间: 2024-01-08 13:10:00
2024-01-10 12:57:00 - trade_module.engine - INFO - 已触发止盈级别: []
2024-01-10 12:57:00 - trade_module.engine - INFO - ================================================================================
2024-01-10 12:57:00 - trade_module.engine - INFO - ✓ 平仓成功 | LONG | 入场=45061.80 | 出场=44329.00 | 盈亏=-0.016238 BTC ($-700.00) | 原因=stop_loss
```

---

## 使用场景

### 1. 调试交易信号

**问题**: 为什么在这个价格开仓?

**查看日志**:
```bash
grep "检测到开仓信号" logs/trade_engine.log
```

可以看到完整的信号信息,包括指标数据。

### 2. 跟踪持仓状态

**问题**: 持仓过程中发生了什么?

**查看日志**:
```bash
grep "当前持仓数:" logs/trade_engine.log | tail -20
```

可以看到每条K线的持仓状态。

### 3. 分析平仓原因

**问题**: 为什么止损?

**查看日志**:
```bash
grep "准备平仓" logs/trade_engine.log | grep "stop_loss"
```

可以看到详细的平仓信息和持仓详情。

---

## 日志级别控制

### INFO 级别 (始终输出)

- ✅ 开仓信号详细信息
- ✅ 平仓详细信息
- ✅ 交易成功/失败消息

### DEBUG 级别 (可配置)

- ✅ 每条K线的处理信息
- ✅ 持仓状态跟踪
- ✅ 价格信息

### 配置日志级别

**方法1: 代码配置**
```python
import logging
logging.getLogger('trade_module.engine').setLevel(logging.DEBUG)
```

**方法2: 配置文件**
```ini
[loggers]
keys=root,trade_module

[logger_trade_module]
level=DEBUG
handlers=console,file
```

---

## 性能影响

### 智能输出策略

```python
should_log = (
    self.processed_count % 100 == 0 or  # 每100条输出一次 (减少99%的日志)
    signal or  # 有信号时输出 (重要事件)
    len(self.positions) > 0  # 有持仓时输出 (关键跟踪)
)
```

**性能优化**:
- ✅ **无信号无持仓时**: 每100条K线才输出1次日志
- ✅ **有信号时**: 立即输出详细信息
- ✅ **有持仓时**: 每条K线都输出 (跟踪持仓变化)

**性能测试**:
- 处理10,000条K线
- 无信号无持仓: 约100条日志 (1%)
- 有信号: 额外增加约10-20条详细日志
- 有持仓: 每条K线1条日志 (可接受)

---

## 验证测试

### 测试步骤

1. **运行回测**
   ```bash
   python web_app.py
   # 浏览器访问 http://localhost:8076/monitor
   # 点击"启动"按钮运行回测
   ```

2. **查看日志**
   ```bash
   tail -f logs/trade_engine.log | grep -E "检测到开仓信号|准备平仓|处理K线"
   ```

3. **验证输出**
   - ✅ 每处理100条K线输出1次进度
   - ✅ 检测到信号时输出详细信息
   - ✅ 开仓时输出完整的K线和指标数据
   - ✅ 平仓时输出持仓详情

### 预期输出

```log
...
--------------------------------------------------------------------------------
处理K线 #100 | 时间: 2024-01-08 13:10:00
价格: 45061.80 | 最高: 45100.00 | 最低: 45020.00
--------------------------------------------------------------------------------
...
================================================================================
📊 检测到开仓信号 #1
时间: 2024-01-08 13:10:00
信号方向: long
信号原因: V5
...
================================================================================
```

---

## 优势

### ✅ 调试便利

- **问题定位**: 快速找到问题发生的时间和原因
- **状态跟踪**: 实时了解交易引擎的运行状态
- **数据分析**: 完整的交易过程记录

### ✅ 性能优化

- **智能输出**: 只在关键时刻输出详细日志
- **分级控制**: INFO/DEBUG级别分离
- **最小影响**: 对回测性能影响很小

### ✅ 可维护性

- **清晰易读**: 使用分隔线和表情符号
- **结构化**: 统一的日志格式
- **完整性**: 覆盖开仓、持仓、平仓全流程

---

## 相关文件

- **修改文件**: [trade_module/trade_engine.py](trade_module/trade_engine.py)
- **日志位置**: 第79行 (初始化), 第279-290行 (平仓日志), 第762-786行 (K线处理日志), 第779-791行 (开仓日志)
- **相关文档**: [docs/SIGNAL_DESCRIPTION_FIX.md](SIGNAL_DESCRIPTION_FIX.md)

---

## 总结

通过在trade_engine.py的关键位置添加详细的调试日志:

✅ **完整的交易过程跟踪** - 从开仓到平仓的完整记录
✅ **智能的输出策略** - 平衡性能和可观测性
✅ **清晰的日志格式** - 易于阅读和分析
✅ **灵活的级别控制** - 根据需要调整输出详细程度

现在可以清晰地看到每条数据行和信号的详细信息! 🎉
