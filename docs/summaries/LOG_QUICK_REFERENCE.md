# 日志系统快速参考

## 快速开始

### 1. 导入日志模块
```python
from core.logger import get_logger

logger = get_logger('your_module_name')
```

### 2. 记录日志
```python
logger.info("信息日志")
logger.warning("警告日志")
logger.error("错误日志")
logger.debug("调试日志")
```

## 日志模块使用统计

### 已集成模块 (20个)

| 模块 | 日志名称 | 主要日志内容 |
|------|---------|-------------|
| main | main | 程序启动/关闭,模块初始化 |
| simple_replay | simple_replay | 回测进度,数据统计 |
| verify_replay | verify_replay | 数据验证 |
| replay_engine | data_module.replay | 回测主循环,K线处理 |
| indicator_calculator | data_module.indicator | 指标计算,预热数据 |
| kline_fetcher | data_module.kline_fetcher | K线获取,API请求 |
| data_writer | data_module.writer | 数据写入 |
| data_notifier | data_module.notifier | 数据通知 |
| signal_calculator | signal_module.calculator | 信号计算 |
| position_manager | signal_module.position | 持仓管理 |
| tp_manager | signal_module.tp | 止盈管理 |
| sl_manager | signal_module.sl | 止损管理 |
| local_order | trade_module.order | 订单管理 |
| account_tracker | trade_module.account | 账户追踪 |
| order_executor | trade_module.executor | 订单执行 |
| web_interface | interaction_module.web | Web服务 |
| feishu_bot | interaction_module.feishu | 飞书通知 |

### 日志文件示例
```
data/logs/
├── main_20260105.log
├── simple_replay_20260105.log
├── data_module_replay_20260105.log
├── signal_module_position_20260105.log
├── trade_module_order_20260105.log
└── ...
```

## 常用日志命令

### 查看实时日志
```bash
# 查看所有日志
tail -f data/logs/*.log

# 查看特定模块日志
tail -f data/logs/simple_replay_*.log

# 查看错误日志
tail -f data/logs/*.log | grep ERROR
```

### 搜索日志
```bash
# 搜索错误
grep ERROR data/logs/*.log

# 搜索特定关键词
grep "创建订单" data/logs/trade_module_order_*.log

# 查看最近20行日志
tail -20 data/logs/main_*.log
```

### 统计日志
```bash
# 统计错误数量
grep -c ERROR data/logs/*.log

# 查看各级别日志统计
for level in DEBUG INFO WARNING ERROR CRITICAL; do
    echo "$level: $(grep -c $level data/logs/*.log)"
done
```

## 日志级别选择

| 级别 | 使用场景 | 示例 |
|------|---------|------|
| DEBUG | 调试信息 | `logger.debug(f"变量值: {x}")` |
| INFO | 正常业务流程 | `logger.info("回测开始")` |
| WARNING | 警告但不影响运行 | `logger.warning("数据延迟")` |
| ERROR | 错误但可继续 | `logger.error(f"操作失败: {e}")` |
| CRITICAL | 严重错误,无法继续 | `logger.critical("数据库损坏")` |

## 日志格式

### 标准格式
```
2026-01-05 21:51:26 - module_name - LEVEL - message
```

### 实际示例
```
2026-01-05 21:51:26 - simple_replay - INFO - 回测时间: 2024-01-01T00:00:00 至 2024-01-03T23:59:59
2026-01-05 21:51:26 - simple_replay - INFO - 预热天数: 200天 (支持1天MACD计算)
2026-01-05 21:51:26 - simple_replay - INFO - ✓ 加载预热数据: 288,000条
2026-01-05 21:51:26 - simple_replay - INFO - 已处理 500 条K线, 当前时间: 2024-01-01T08:19:00
2026-01-05 21:51:26 - simple_replay - INFO - 回测完成
```

## 日志最佳实践

### ✅ 推荐
```python
# 1. 使用模块化命名
logger = get_logger('data_module.replay')

# 2. 包含关键信息
logger.info(f"创建订单: {order_type} {contracts}@{price}")

# 3. 记录异常堆栈
try:
    operation()
except Exception as e:
    logger.error(f"操作失败: {e}", exc_info=True)

# 4. 记录性能数据
start = time.time()
# ... 操作 ...
logger.info(f"操作完成, 耗时: {time.time()-start:.2f}秒")
```

### ❌ 不推荐
```python
# 1. 使用非模块化命名
logger = get_logger('my_logger')

# 2. 缺少关键信息
logger.info("订单创建成功")

# 3. 滥用DEBUG级别
logger.debug("回测开始")  # 应该用INFO

# 4. 不记录异常堆栈
logger.error(f"操作失败: {e}")  # 应该加上 exc_info=True
```

## 相关文档

- [LOG_INTEGRATION.md](LOG_INTEGRATION.md) - 完整的日志集成说明
- [core/logger.py](core/logger.py) - 日志模块实现

## 日志管理

### 日志轮转
- 单文件最大: 10MB
- 备份数量: 5个
- 自动轮转: 是

### 日志清理
```bash
# 删除30天前的日志
find data/logs -name "*.log" -mtime +30 -delete

# 清空所有日志
rm -rf data/logs/*.log
```

### 日志备份
```bash
# 备份日志
tar -czf logs_backup_$(date +%Y%m%d).tar.gz data/logs/

# 解压备份
tar -xzf logs_backup_20260105.tar.gz
```

## 更新日期
2026-01-05
