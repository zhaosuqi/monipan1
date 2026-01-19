# 数据库回测模式显示修复

## 问题

选择数据库回测模式后，监控页面仍然显示"模拟盘"而不是"数据库回测模式"。

## 原因

**web_app.py** 中的 `bot_state` 初始化时硬编码为 `'live'` 模式，导致即使配置了数据库回测模式，监控页面也显示错误的模式。

### 问题代码

```python
# 修复前
bot_state = {
    'running': False,
    'mode': 'live',  # ❌ 硬编码，不随配置变化
    'start_time': None,
    'connected': False
}
```

## 解决方案

### 1. 修改初始化

将 `bot_state` 的模式初始化为 `None`，表示将在运行时动态获取：

```python
# 修复后
bot_state = {
    'running': False,
    'mode': None,  # ✓ 将在访问时动态获取
    'start_time': None,
    'connected': False
}
```

### 2. 修改API逻辑

在 `/api/bot/state` 接口中，动态获取当前配置的模式：

```python
@app.route('/api/bot/state', methods=['GET'])
def get_bot_state():
    """获取机器人状态"""
    # 动态获取当前模式
    current_mode = get_current_mode()

    # 如果机器人未运行，使用当前配置的模式
    # 如果机器人正在运行，使用启动时设置的模式
    state_to_return = bot_state.copy()
    if not state_to_return['running']:
        state_to_return['mode'] = current_mode

    return jsonify({
        'success': True,
        'data': state_to_return
    })
```

### 3. 模式检测逻辑

使用环境变量动态检测模式：

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

## 验证测试

### 测试脚本

```bash
./test_backtest_mode_fix.sh
```

### 测试结果

```
✓✓✓ 修复成功！
✓ 配置模式正确: backtest
✓ 机器人状态模式正确: backtest
```

### API响应

```json
// 配置模式 API
{
    "data": {
        "mode": "backtest",
        "mode_name": "数据库回测模式"
    },
    "success": true
}

// 机器人状态 API
{
    "data": {
        "connected": false,
        "mode": "backtest",
        "running": false,
        "start_time": null
    },
    "success": true
}
```

## 使用方法

### 启动数据库回测模式

```bash
# 方式1: 使用专用脚本
./start_web_backtest.sh

# 方式2: 手动设置环境变量
export DB_SIM_MODE=1
export REPLAY_MODE=1
python web_app.py
```

### 访问监控页面

```
http://localhost:8076/monitor
```

**现在应该正确显示:**
- 运行模式: **数据库回测模式**
- 而不是: 模拟盘

### 模式对应关系

| 环境变量 | 模式值 | 显示名称 |
|---------|--------|----------|
| DB_SIM_MODE=1 或 REPLAY_MODE=1 | backtest | 数据库回测模式 |
| BINANCE_TESTNET=1 | simulation | 模拟盘 |
| 默认配置 | live | 实盘模式 |

## 相关文件

### 修改的文件

1. **web_app.py**
   - 第34行: 修改 `bot_state` 初始化
   - 第356-371行: 修改 `/api/bot/state` API

### 新增的文件

1. **test_backtest_mode_fix.sh** - 测试脚本
2. **docs/MODE_FIX_SUMMARY.md** - 本文档

### 相关脚本

1. **switch_to_backtest_mode.sh** - 切换模式脚本
2. **start_web_backtest.sh** - 启动服务脚本

## 测试验证

### 快速测试

```bash
# 1. 启动服务
./start_web_backtest.sh

# 2. 测试API
curl http://localhost:8076/api/bot/state

# 3. 在浏览器访问
# http://localhost:8076/monitor

# 4. 检查显示
# 应该显示"数据库回测模式"
```

### 完整测试

```bash
./test_backtest_mode_fix.sh
```

## 注意事项

1. **模式切换后需要重启服务**
   - 修改环境变量后
   - 必须重启Web服务
   - 才能生效

2. **机器人运行时锁定模式**
   - 机器人启动时，模式会被锁定
   - 运行中无法切换模式
   - 需要先停止机器人

3. **环境变量优先级**
   - 环境变量 > 配置文件默认值
   - DB_SIM_MODE 和 REPLAY_MODE 任一为1就是回测模式

## 故障排查

### 问题1: 监控页面还是显示模拟盘

**检查:**
```bash
# 检查环境变量
echo "DB_SIM_MODE: $DB_SIM_MODE"
echo "REPLAY_MODE: $REPLAY_MODE"

# 检查API
curl http://localhost:8076/api/bot/state | python -m json.tool
```

**解决:**
```bash
# 确保设置正确
export DB_SIM_MODE=1
export REPLAY_MODE=1

# 重启服务
lsof -ti :8076 | xargs kill -9
./start_web_backtest.sh
```

### 问题2: API返回错误模式

**检查:**
```bash
# 查看Web服务日志
tail -f /tmp/web_backtest.log
```

**可能原因:**
- 环境变量未生效
- 服务未重启
- 配置文件错误

## 更新日志

### v1.0.1 (2026-01-06)

**修复:**
- ✅ 修复监控页面模式显示问题
- ✅ 动态获取当前配置模式
- ✅ API返回正确的模式信息

**新增:**
- ✅ 模式显示测试脚本
- ✅ 详细的使用说明

## 总结

**问题已解决！** ✅

现在：
- ✅ 配置页面显示正确的模式
- ✅ 监控页面显示正确的模式
- ✅ API返回正确的模式信息
- ✅ 数据库回测模式正常工作

**开始使用:**

```bash
./start_web_backtest.sh
```

访问: **http://localhost:8076/monitor**

应该正确显示: **数据库回测模式** 🎯
