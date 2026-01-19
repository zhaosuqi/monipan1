# 日志模块集成说明

## 日志系统架构

### 核心组件
- **[core/logger.py](core/logger.py)** - 日志管理模块
- **日志目录**: `data/logs/`
- **日志级别**: DEBUG, INFO, WARNING, ERROR, CRITICAL

### 日志配置

#### 自动配置
日志系统会自动:
- 创建日志目录 `data/logs/`
- 按日期分割日志文件
- 单个日志文件最大 10MB
- 保留最近 5 个备份文件

#### 日志格式
```
YYYY-MM-DD HH:MM:SS - module_name - LEVEL - message
```

示例:
```
2026-01-05 21:51:26 - simple_replay - INFO - 回测时间: 2024-01-01T00:00:00 至 2024-01-03T23:59:59
```

## 已集成日志的模块

### 1. 核心模块

#### core/logger.py
```python
from core.logger import get_logger

logger = get_logger('module_name')
logger.info("信息日志")
logger.error("错误日志")
logger.debug("调试日志")
```

### 2. 数据模块 (data_module/)

#### kline_fetcher.py
```python
self.logger = get_logger('data_module.kline_fetcher')
```
- 获取K线数据
- API请求失败
- 数据转换日志

#### indicator_calculator.py
```python
self.logger = get_logger('data_module.indicator')
```
- 指标初始化
- 预热数据加载
- 指标计算完成

#### data_writer.py
```python
self.logger = get_logger('data_module.writer')
```
- 数据写入
- 数据库操作

#### data_notifier.py
```python
self.logger = get_logger('data_module.notifier')
```
- 订阅通知
- 数据分发

#### replay_engine.py
```python
self.logger = get_logger('data_module.replay')
```
- 回测开始/结束
- 数据加载进度
- K线处理统计
- 交易日志记录

### 3. 信号模块 (signal_module/)

#### signal_calculator.py
```python
self.logger = get_logger('signal_module.calculator')
```
- 信号计算
- 开仓/平仓信号

#### position_manager.py
```python
self.logger = get_logger('signal_module.position')
```
- 添加持仓: `logger.info(f"添加持仓: {side} {contracts}@{price}")`
- 关闭持仓: `logger.info(f"关闭持仓: {side} {contracts}@{price}")`

#### tp_manager.py
```python
self.logger = get_logger('signal_module.tp')
```
- 止盈目标计算
- 止盈触发

#### sl_manager.py
```python
self.logger = get_logger('signal_module.sl')
```
- 止损价格计算
- 止损触发

### 4. 交易模块 (trade_module/)

#### local_order.py
```python
self.logger = get_logger('trade_module.order')
```
- 创建订单: `logger.info(f"创建订单: {order_type} {contracts}@{price}")`
- 订单失败: `logger.error(f"创建订单失败: {e}")`
- 更新订单状态

#### account_tracker.py
```python
self.logger = get_logger('trade_module.account')
```
- 余额更新: `logger.info(f"更新余额: {balance} BTC")`
- 盈亏记录: `logger.info(f"实现盈亏: {pnl:.2f} USD, 总计: {total:.2f} USD")`

#### order_executor.py
```python
self.logger = get_logger('trade_module.executor')
```
- 开仓订单执行
- 止盈订单执行
- 止损订单执行

### 5. 交互模块 (interaction_module/)

#### web_interface.py
```python
self.logger = get_logger('interaction_module.web')
```
- Web服务启动: `logger.info(f"启动Web服务: {host}:{port}")`

#### feishu_bot.py
```python
self.logger = get_logger('interaction_module.feishu')
```
- 消息发送成功: `logger.debug(f"飞书消息发送成功: {message[:50]}")`
- 发送失败: `logger.error(f"飞书消息发送失败: {status_code}")`
- 发送异常: `logger.error(f"飞书消息发送异常: {e}")`

### 6. 主程序

#### main.py
```python
logger = get_logger('main')
```
- 程序启动/关闭
- 模块初始化
- 错误处理

#### simple_replay.py
```python
logger = get_logger('simple_replay')
```
- 回测进度
- 数据处理统计
- 回测结果

## 日志级别使用指南

### DEBUG
详细的调试信息,通常只在开发时使用:
```python
logger.debug(f"飞书消息发送成功: {message[:50]}")
logger.debug(f"指标计算结果: {indicators}")
```

### INFO
一般信息,记录正常的业务流程:
```python
logger.info("回测开始")
logger.info(f"添加持仓: {side} {contracts}@{price}")
logger.info(f"处理K线数: {count}")
```

### WARNING
警告信息,不影响程序运行但需要注意:
```python
logger.warning(f"未获取到K线数据")
logger.warning(f"指标计算延迟")
```

### ERROR
错误信息,程序遇到错误但可以继续:
```python
logger.error(f"创建订单失败: {e}")
logger.error(f"数据库连接失败: {e}")
```

### CRITICAL
严重错误,程序无法继续运行:
```python
logger.critical(f"数据库损坏,无法启动")
logger.critical(f"配置文件缺失")
```

## 日志文件管理

### 文件命名规则
```
{module_name}_{YYYYMMDD}.log
```

示例:
```
simple_replay_20260105.log
main_20260105.log
signal_module_calculator_20260105.log
```

### 日志轮转
- 单个日志文件最大 10MB
- 超过10MB会自动创建新文件
- 旧文件会被重命名为 `.log.1`, `.log.2` 等
- 最多保留 5 个备份文件

### 查看日志

#### 实时查看
```bash
# 查看特定模块的日志
tail -f data/logs/simple_replay_20260105.log

# 查看所有日志
tail -f data/logs/*.log
```

#### 搜索日志
```bash
# 搜索错误日志
grep ERROR data/logs/*.log

# 搜索特定关键词
grep "创建订单" data/logs/trade_module_order_*.log

# 查看最近的错误
grep ERROR data/logs/main_*.log | tail -20
```

#### 统计日志
```bash
# 统计各级别日志数量
for level in DEBUG INFO WARNING ERROR CRITICAL; do
    echo "$level:"
    grep "$level" data/logs/*.log | wc -l
done
```

## 日志最佳实践

### 1. 统一日志命名
使用模块化命名:
```python
# ✅ 推荐
logger = get_logger('data_module.replay')

# ❌ 不推荐
logger = get_logger('my_logger')
```

### 2. 适当的日志级别
```python
# ✅ 正确使用
logger.info("回测开始")  # 正常业务流程
logger.error(f"数据库错误: {e}")  # 错误信息

# ❌ 滥用级别
logger.debug("回测开始")  # 重要信息不应该用DEBUG
logger.info(f"变量x的值: {x}")  # 调试信息应该用DEBUG
```

### 3. 包含关键信息
```python
# ✅ 包含关键上下文
logger.info(f"创建订单: {order_type} {contracts}@{price}")

# ❌ 缺少关键信息
logger.info("订单创建成功")
```

### 4. 异常日志
```python
# ✅ 记录完整异常堆栈
try:
    risky_operation()
except Exception as e:
    logger.error(f"操作失败: {e}", exc_info=True)

# ❌ 只记录异常消息
except Exception as e:
    logger.error(f"操作失败: {e}")
```

### 5. 性能日志
```python
import time

start = time.time()
# ... 执行操作 ...
duration = time.time() - start
logger.info(f"操作完成, 耗时: {duration:.2f}秒")
```

## 日志监控与告警

### 监控关键错误
```bash
# 持续监控ERROR级别日志
tail -f data/logs/*.log | grep --line-buffered ERROR
```

### 日志告警脚本
```bash
#!/bin/bash
# log_alert.sh

LOG_FILE="data/logs/main_$(date +%Y%m%d).log"
ERROR_COUNT=$(grep -c ERROR "$LOG_FILE")

if [ $ERROR_COUNT -gt 10 ]; then
    echo "警告: 检测到 $ERROR_COUNT 个错误!"
    # 发送告警通知
fi
```

## 调试技巧

### 1. 启用DEBUG日志
修改日志级别:
```python
# core/logger.py
console_handler.setLevel(logging.DEBUG)  # 改为DEBUG
```

### 2. 过滤日志
```bash
# 只看特定模块的日志
grep "data_module.replay" data/logs/*.log

# 只看最近1小时的日志
find data/logs -name "*.log" -mmin -60 -exec cat {} \;
```

### 3. 日志分析
```python
import re
from collections import Counter

# 分析最常见的错误
with open('data/logs/main_20260105.log') as f:
    errors = [line for line in f if 'ERROR' in line]
    error_messages = [re.search(r'ERROR - (.+)', e).group(1) for e in errors]
    print(Counter(error_messages).most_common(10))
```

## 相关文件

- [core/logger.py](core/logger.py) - 日志模块实现
- [core/config.py](core/config.py) - 日志目录配置
- [data/logs/](data/logs/) - 日志文件目录

## 更新日期

2026-01-05
