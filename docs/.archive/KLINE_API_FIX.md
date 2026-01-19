# K线API错误修复报告

## 问题描述

在数据库回测模式下，访问监控页面时报错：

```
获取失败: API.__init__() got an unexpected keyword argument 'testnet'
```

## 问题原因

### 1. KlineFetcher 的 testnet 参数错误

**文件:** `data_module/kline_fetcher.py`

**问题代码:**
```python
self.client = CMFutures(
    key=config.BINANCE_API_KEY,
    secret=config.BINANCE_API_SECRET,
    testnet=config.BINANCE_TESTNET  # ❌ CMFutures不支持testnet参数
)
```

**说明:**
- `binance.cm_futures.CMFutures` 的 `__init__()` 方法不支持 `testnet` 参数
- 在数据库回测模式下，虽然不会调用Binance API，但数据源适配器初始化时仍会创建 `KlineFetcher`

### 2. 全局数据源单例不更新

**文件:** `data_module/data_source_adapter.py`

**问题:**
- 全局单例 `_data_source` 在第一次创建后就固定了
- 切换模式后，单例不会重新创建
- 导致在数据库回测模式下仍尝试创建 `KlineFetcher`

## 解决方案

### 修复1: KlineFetcher 测试网配置

**文件:** `data_module/kline_fetcher.py:19-36`

```python
def __init__(self):
    self.logger = get_logger('data_module.kline_fetcher')

    # 根据是否测试网选择不同的端点
    if config.BINANCE_TESTNET:
        # 测试网
        self.client = CMFutures(
            key=config.BINANCE_API_KEY,
            secret=config.BINANCE_API_SECRET
        )
        # 设置测试网端点
        self.client.base_url = 'https://testnet.binancefuture.com'
    else:
        # 实盘
        self.client = CMFutures(
            key=config.BINANCE_API_KEY,
            secret=config.BINANCE_API_SECRET
        )
```

**改进:**
- ✅ 移除了不支持的 `testnet` 参数
- ✅ 使用 `base_url` 属性设置端点
- ✅ 测试网和实盘分别处理

### 修复2: 数据源单例自动更新

**文件:** `data_module/data_source_adapter.py:219-235`

```python
def get_data_source() -> DataSourceAdapter:
    """
    获取全局数据源实例（单例模式）

    每次调用时检查当前模式，如果模式变化则重新创建
    """
    global _data_source
    current_mode = get_current_mode()

    # 如果单例不存在或模式不匹配，重新创建
    if _data_source is None or _data_source.mode != current_mode:
        _data_source = DataSourceAdapter(mode=current_mode)

    return _data_source
```

**改进:**
- ✅ 每次调用时检查当前模式
- ✅ 模式变化时自动重新创建
- ✅ 避免在数据库回测模式下创建 `KlineFetcher`

## 测试验证

### 测试脚本

```bash
./test_kline_api_fix.sh
```

### 测试结果

```
✓✓✓ K线API测试成功！
✓ 成功获取K线数据
✓ 数据库回测模式正常工作
✓ 第一条K线时间: 2023-01-01T00:00:00
```

### API响应

```json
{
    "data": [
        {
            "close": 16531.1,
            "high": 16531.2,
            "low": 16531.1,
            "open": 16531.2,
            "time": "2023-01-01T00:00:00",
            "volume": 132.0
        },
        ...
    ],
    "success": true
}
```

### 日志输出

```
2026-01-06 11:55:47 - data_module.data_source_adapter - INFO - 初始化数据源适配器，模式: replay
2026-01-06 11:55:47 - data_module.db_kline_reader - INFO - 初始化数据库K线读取器
2026-01-06 11:55:47 - data_module.db_kline_reader - INFO - 数据库路径: /Users/zhaosuqi/work/monipan/data/klines.db
2026-01-06 11:55:47 - data_module.db_kline_reader - INFO - 表 klines_1m 验证通过
2026-01-06 11:55:47 - data_module.data_source_adapter - INFO - 使用SQLite数据库数据源
```

## 修复效果

### 修复前

- ❌ 监控页面报错: `testnet` 参数错误
- ❌ 无法获取K线数据
- ❌ 数据库回测模式无法使用

### 修复后

- ✅ 监控页面正常工作
- ✅ 成功获取K线数据（从SQLite）
- ✅ 数据库回测模式完全可用
- ✅ 自动根据模式切换数据源

## 数据源切换逻辑

### 自动检测

```python
def get_current_mode():
    """获取当前运行模式"""
    if config.DB_SIM_MODE or config.REPLAY_MODE:
        return 'backtest'
    elif config.BINANCE_TESTNET:
        return 'simulation'
    else:
        return 'live'
```

### 数据源选择

| 模式 | 数据源 | 来源 |
|------|--------|------|
| backtest | DbKlineReader | SQLite数据库 |
| simulation/live | KlineFetcher | Binance API |

## 使用方法

### 启动数据库回测模式

```bash
./start_web_backtest.sh
```

### 访问监控页面

```
http://localhost:8076/monitor
```

**现在应该:**
- ✅ 正确显示"数据库回测模式"
- ✅ 成功加载K线图
- ✅ 显示历史K线数据

## 相关文件

### 修改的文件

1. **data_module/kline_fetcher.py**
   - 移除 `testnet` 参数
   - 使用 `base_url` 设置端点

2. **data_module/data_source_adapter.py**
   - 改进 `get_data_source()` 函数
   - 自动检测模式变化

### 新增的文件

1. **test_kline_api_fix.sh** - 测试脚本
2. **docs/KLINE_API_FIX.md** - 本文档

## 技术细节

### CMFutures 端点配置

**测试网:**
```python
client = CMFutures(key=api_key, secret=api_secret)
client.base_url = 'https://testnet.binancefuture.com'
```

**实盘:**
```python
client = CMFutures(key=api_key, secret=api_secret)
# 使用默认端点: https://dbinancefuture.com
```

### 数据源适配器模式

**replay 模式 (数据库回测):**
```python
DataSourceAdapter(mode='replay')
  └─> DbKlineReader(db_path='data/klines.db')
      └─> 从SQLite读取历史数据
```

**live/simulation 模式 (实盘/模拟):**
```python
DataSourceAdapter(mode='live')
  └─> KlineFetcher()
      └─> 从Binance API获取实时数据
```

## 注意事项

1. **模式切换需要重启**
   - 修改环境变量后
   - 必须重启Web服务
   - 单例才会更新

2. **数据库要求**
   - 数据库文件必须存在
   - 表结构必须正确
   - 数据格式必须匹配

3. **API密钥**
   - 实盘/模拟盘模式需要API密钥
   - 数据库回测模式不需要

## 故障排查

### 问题1: 仍然报 testnet 错误

**原因:** 旧的服务进程还在运行

**解决:**
```bash
# 停止旧进程
lsof -ti :8076 | xargs kill -9

# 重启服务
./start_web_backtest.sh
```

### 问题2: 无法获取K线数据

**检查:**
```bash
# 检查数据库
sqlite3 data/klines.db "SELECT COUNT(*) FROM klines_1m"

# 检查模式
curl http://localhost:8076/api/config/mode

# 查看日志
tail -f /tmp/web_backtest.log
```

## 总结

**问题已完全解决！** ✅

修复内容:
- ✅ 修复 `KlineFetcher` 的 `testnet` 参数错误
- ✅ 改进数据源单例的自动更新机制
- ✅ 数据库回测模式完全可用

现在可以:
- ✅ 在数据库回测模式下正常使用监控页面
- ✅ 查看历史K线图表
- ✅ 监控回测订单和状态

**立即开始使用:**

```bash
./start_web_backtest.sh
```

访问: **http://localhost:8076/monitor** 🚀
