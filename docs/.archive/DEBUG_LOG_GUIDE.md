# 调试日志说明文档

## 日期
2026-01-07

## 目的
增加详细的调试日志，用于排查2024-01-01 18:42:00和19:39:59这两个时间点不开仓的原因。

---

## 修改的文件

### 1. signal_module/signal_calculator.py

#### 修改1: calculate_open_signal方法添加时间戳参数

**位置**: Line 185-202

**修改内容**:
- 提取时间戳字符串用于调试
- 对特定时间（18:42或19:39）输出详细的K线数据
- 传递ts_str参数到_check_long_signal方法

**日志输出示例**:
```
🔍 [信号计算] 2024-01-01 18:42:00 | H15=40.73 H1H=42.75 H4=99.49 H1D=-237.52 | J15=109.73 J1H=94.70 J4H=101.06
```

#### 修改2: _check_long_signal方法添加调试模式

**位置**: Line 239-258

**修改内容**:
- 添加ts_str参数
- 设置debug_mode，针对18:42和19:39两个时间点启用详细日志

**新增的日志点**:

1. **HIST15限制检查** (Line 262-268)
```python
logger.info(f"✅ [{ts_str}] HIST15限制: {hist15:.2f} 在范围内")
logger.warning(f"❌ [{ts_str}] HIST15限制: {hist15:.2f} 超出范围")
```

2. **HIST1D均值检查1** (Line 381-394)
```python
logger.info(f"✅ [{ts_str}] HIST1D均值1通过: {hist1d:.2f} - 0 >= {hist1d_mean:.2f}")
logger.warning(f"❌ [{ts_str}] HIST1D均值1拒绝: {hist1d:.2f} - 0 < {hist1d_mean:.2f}")
```

3. **HIST1D均值检查2** (Line 396-409)
```python
logger.info(f"✅ [{ts_str}] HIST1D均值2通过: {hist1d:.2f} - 1 >= {hist1d_mean_2:.2f}")
logger.warning(f"❌ [{ts_str}] HIST1D均值2拒绝: {hist1d:.2f} - 1 < {hist1d_mean_2:.2f}")
```

4. **J4H检查** (Line 489-495)
```python
logger.info(f"✅ [{ts_str}] J4H检查: {j_4h:.2f} <= {config.T0_J4H_LIMIT}")
logger.warning(f"❌ [{ts_str}] J4H超限: {j_4h:.2f} > {config.T0_J4H_LIMIT}")
```

5. **最终结果** (Line 514-526)
```python
logger.info(f"🎉 [{ts_str}] ✅✅✅ 信号通过所有检查！ ✅✅✅")
logger.warning(f"❌ [{ts_str}] 信号被拒绝，原因: {'; '.join(reasons)}")
```

---

### 2. trade_module/trade_engine.py

#### 修改1: open_position方法添加调试日志

**位置**: Line 125-158, 160-197, 239-240

**新增日志点**:

1. **开仓尝试** (Line 144-145)
```python
logger.info(f"🔍 [开仓尝试] {ts_str} | {side} | 价格={price:.2f} | 信号={signal_name}")
```

2. **资金检查** (Line 153-154)
```python
logger.info(f"💰 [资金检查] 可用资金={available_capital:.6f} BTC")
logger.warning(f"❌ [{ts_str}] 可用资金不足 ({available_capital:.6f} BTC)，跳过开仓")
```

3. **合约计算** (Line 176-177)
```python
logger.info(f"📊 [合约计算] 价格={price:.2f} | 面值={cn} | 最大合约数={max_contracts}")
```

4. **资金不足** (Line 187-196)
```python
logger.warning(f"❌ [{ts_str}] 资金不足，无法开仓...")
```

5. **开仓成功** (Line 239-240)
```python
logger.info(f"✅ [{ts_str}] 🎉 开仓成功！{side} {max_contracts}张 @ {price:.2f}")
```

#### 修改2: process_tick方法添加调试日志

**位置**: Line 784-792, 862-868

**新增日志点**:

1. **tick处理开始** (Line 788-792)
```python
logger.info("=" * 80)
logger.info(f"🔍 [process_tick] {ts_str}")
logger.info(f"🔍 [process_tick] 信号={signal}")
logger.info(f"🔍 [process_tick] 当前持仓数={len(self.positions)}")
```

2. **检测到开仓信号** (Line 862-868)
```python
logger.info(f"可用资金: {self.realized_pnl:.6f} BTC")
logger.info(f"K线数据键: {list(row.keys())}")
```

---

## 使用方法

### 1. 运行回测

```bash
python web_app.py
```

### 2. 查看日志

```bash
# 实时查看日志
tail -f /tmp/web_app.log | grep -E "18:42|19:39|🔍|🎉|❌"

# 只查看特定时间的日志
grep "2024-01-01 18:42" /tmp/web_app.log

# 查看所有调试日志
grep "🔍\|🎉\|❌\|✅" /tmp/web_app.log
```

### 3. 日志分析

日志会显示以下关键信息：

#### 信号计算阶段
```
🔍 [信号计算] 2024-01-01 18:42:00 | H15=40.73 H1H=42.75 H4=99.49 H1D=-237.52 | J15=109.73 J1H=94.70 J4H=101.06
✅ [2024-01-01 18:42:00] HIST15限制: 40.73 在范围内
✅ [2024-01-01 18:42:00] J4H检查: 101.06 <= 113
✅ [2024-01-01 18:42:00] HIST1D均值1通过: -237.52 - 0 >= -273.94
✅ [2024-01-01 18:42:00] HIST1D均值2通过: -237.52 - 1 >= -254.18
🎉 [2024-01-01 18:42:00] ✅✅✅ 信号通过所有检查！ ✅✅✅
```

#### 信号拒绝
```
❌ [2024-01-01 18:42:00] HIST1D均值1拒绝: -237.52 - 0 < -200.00
❌ [2024-01-01 18:42:00] 信号被拒绝，原因: HIST1D均值1: -237.52 < -200.00
```

#### 开仓阶段
```
🔍 [process_tick] 2024-01-01 18:42:00
🔍 [process_tick] 信号=Signal(action='open', side='long')
🔍 [process_tick] 当前持仓数=0
🔍 [开仓尝试] 2024-01-01 18:42:00 | long | 价格=43188.50 | 信号=V5多头信号
💰 [资金检查] 可用资金=1.000000 BTC
📊 [合约计算] 价格=43188.50 | 面值=10000 | 最大合约数=4
✅ [2024-01-01 18:42:00] 🎉 开仓成功！long 4张 @ 43188.50
```

#### 开仓失败原因
```
❌ [2024-01-01 18:42:00] 可用资金不足 (0.000000 BTC)，跳过开仓
❌ [2024-01-01 18:42:00] 跳过开仓: 距离long止损仅5.0分钟 (冷却期60分钟)
❌ [2024-01-01 18:42:00] 资金不足，无法开仓。要求至少=5张
```

---

## 日志级别

### INFO级别
- ✅ 检查通过
- 🔍 调试信息（特定时间）
- 🎉 成功开仓
- 📊 统计信息

### WARNING级别
- ❌ 检查失败
- ❌ 信号被拒绝
- ❌ 开仓失败

### DEBUG级别
- 常规处理流程（每100条输出一次）

---

## 调试时间点

当前只针对以下两个时间点输出详细日志：
- **2024-01-01 18:42:00**
- **2024-01-01 19:39:59**

如果需要调试其他时间，修改以下位置：

### signal_calculator.py
```python
# Line 187
if '18:42' in ts_str or '19:39' in ts_str:
    # 改为
if '目标时间' in ts_str:
```

### trade_engine.py
```python
# Line 127
debug_mode = '18:42' in ts_str or '19:39' in ts_str
# 改为
debug_mode = '目标时间' in ts_str

# Line 786
debug_mode = '18:42' in ts_str or '19:39' in ts_str
# 改为
debug_mode = '目标时间' in ts_str
```

---

## 预期输出

### 情况1: 信号通过并成功开仓
```
🔍 [信号计算] 2024-01-01 18:42:00 | ...
✅ [2024-01-01 18:42:00] HIST15限制: 40.73 在范围内
✅ [2024-01-01 18:42:00] HIST1D均值1通过: -237.52 >= -273.94
✅ [2024-01-01 18:42:00] J4H检查: 101.06 <= 113
🎉 [2024-01-01 18:42:00] ✅✅✅ 信号通过所有检查！ ✅✅✅
🔍 [process_tick] 2024-01-01 18:42:00
🔍 [process_tick] 信号=Signal(action='open', side='long')
🔍 [开仓尝试] 2024-01-01 18:42:00 | long | 价格=43188.50
💰 [资金检查] 可用资金=1.000000 BTC
📊 [合约计算] 价格=43188.50 | 面值=10000 | 最大合约数=4
✅ [2024-01-01 18:42:00] 🎉 开仓成功！long 4张 @ 43188.50
```

### 情况2: 信号被拒绝
```
🔍 [信号计算] 2024-01-01 18:42:00 | ...
✅ [2024-01-01 18:42:00] HIST15限制: 40.73 在范围内
❌ [2024-01-01 18:42:00] HIST1D均值1拒绝: -237.52 < -200.00
❌ [2024-01-01 18:42:00] 信号被拒绝，原因: HIST1D均值1: -237.52 < -200.00
```

### 情况3: 信号通过但开仓失败
```
🎉 [2024-01-01 18:42:00] ✅✅✅ 信号通过所有检查！ ✅✅✅
🔍 [process_tick] 2024-01-01 18:42:00
🔍 [process_tick] 信号=Signal(action='open', side='long')
🔍 [开仓尝试] 2024-01-01 18:42:00 | long | 价格=43188.50
❌ [2024-01-01 18:42:00] 可用资金不足 (0.000000 BTC)，跳过开仓
```

---

## 排查步骤

1. **检查是否有信号**
   - 搜索 "🔍 [信号计算]"
   - 如果没有，说明信号计算器没有被调用

2. **检查信号是否通过**
   - 搜索 "🎉" 表示通过
   - 搜索 "❌" 表示被拒绝
   - 查看拒绝原因

3. **检查是否调用开仓**
   - 搜索 "🔍 [process_tick]" 后应该有 "🔍 [开仓尝试]"
   - 如果没有，检查是否已有持仓

4. **检查开仓结果**
   - 搜索 "🎉 开仓成功" 表示成功
   - 搜索 "❌" + "可用资金不足" 或其他失败原因

---

## 注意事项

1. **日志文件位置**: `/tmp/web_app.log`
2. **日志级别**: 当前使用INFO和WARNING，确保在配置中启用
3. **性能影响**: 只对特定时间点启用详细日志，对整体性能影响很小
4. **清理**: 完成调试后可以保留这些日志，方便后续排查类似问题

---

## 相关文件

- **信号计算器**: [signal_module/signal_calculator.py](signal_module/signal_calculator.py)
- **交易引擎**: [trade_module/trade_engine.py](trade_module/trade_engine.py)
- **回测会话**: [trade_module/backtest_session.py](trade_module/backtest_session.py)
- **Web应用**: [web_app.py](web_app.py)

---

**调试日志已添加！运行回测后查看日志即可看到详细的执行过程。**
