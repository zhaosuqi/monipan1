# 配置页面模式显示修复

## 问题描述

在配置页面切换到数据库回测模式后，返回页面时默认显示为模拟盘模式，而不是数据库回测模式。

## 问题原因

### 1. 模板渲染时的配置判断

**问题代码:**
```django
{{ config.DB_SIM_MODE or config.REPLAY_MODE and '数据库回测模式' or '实盘模式' }}
```

**问题:**
- 没有考虑模拟盘的情况
- 判断逻辑不完整

### 2. JavaScript使用服务器端渲染的值

**问题:**
```javascript
let currentMode = '{{ "backtest" if config.DB_SIM_MODE or config.REPLAY_MODE else "simulation" if config.BINANCE_TESTNET else "live" }}';
```

- 使用页面加载时的配置值
- 切换模式后，页面不刷新的话值不会更新

### 3. 模式切换时未更新所有配置

**问题:**
- 只更新了部分环境变量
- 没有更新 `config` 对象
- 没有重置数据源单例

## 解决方案

### 修复1: 改进模板判断逻辑

**文件:** `web/templates/config.html:26`

```django
{{ '数据库回测模式' if (config.DB_SIM_MODE or config.REPLAY_MODE) else '模拟盘模式' if config.BINANCE_TESTNET else '实盘模式' }}
```

### 修复2: 从API动态获取当前模式

**文件:** `web/templates/config.html:170-199`

```javascript
// 页面加载时从API获取当前模式
document.addEventListener('DOMContentLoaded', function() {
    fetch('/api/config/mode')
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                currentMode = data.data.mode;
                highlightCurrentMode();
                updateCurrentModeDisplay(data.data.mode_name);
            }
        })
        .catch(err => {
            // 使用服务器端渲染的值作为后备
            currentMode = '{{ "backtest" if (...) else "simulation" if (...) else "live" }}';
            highlightCurrentMode();
        });
});
```

### 修复3: 完整更新模式配置

**文件:** `web_app.py:107-137`

```python
# 保存到环境变量
if mode == 'live':
    os.environ['DB_SIM_MODE'] = '0'
    os.environ['REPLAY_MODE'] = '0'
    os.environ['BINANCE_TESTNET'] = '0'
    # 更新config对象
    config.DB_SIM_MODE = False
    config.REPLAY_MODE = False
    config.BINANCE_TESTNET = False
elif mode == 'simulation':
    os.environ['DB_SIM_MODE'] = '0'
    os.environ['REPLAY_MODE'] = '0'
    os.environ['BINANCE_TESTNET'] = '1'
    # 更新config对象
    config.DB_SIM_MODE = False
    config.REPLAY_MODE = False
    config.BINANCE_TESTNET = True
elif mode == 'backtest':
    os.environ['DB_SIM_MODE'] = '1'
    os.environ['REPLAY_MODE'] = '1'
    os.environ['BINANCE_TESTNET'] = '0'
    # 更新config对象
    config.DB_SIM_MODE = True
    config.REPLAY_MODE = True
    config.BINANCE_TESTNET = False

# 重置数据源单例
from data_module.data_source_adapter import reset_data_source
reset_data_source()
```

## 测试验证

### 测试结果

```
✓✓✓ 所有测试通过！
✓ 初始模式正确: 数据库回测模式
✓ 切换到模拟盘模式成功
✓ 切换回数据库回测模式成功
✓ 配置页面会正确显示当前模式
```

### 测试步骤

1. **初始状态:** 数据库回测模式 ✓
2. **切换到模拟盘:** 模拟盘模式 ✓
3. **切换回数据库:** 数据库回测模式 ✓
4. **K线数据:** 从数据库获取 ✓

## 修复效果

### 修复前

- ❌ 配置页面显示不正确
- ❌ 切换模式后返回页面显示错误
- ❌ 需要刷新页面才能看到正确模式

### 修复后

- ✅ 配置页面始终显示正确模式
- ✅ 切换模式后立即更新显示
- ✅ 页面加载时从API获取最新模式
- ✅ 所有环境变量同步更新

## 相关文件

### 修改的文件

1. **web/templates/config.html**
   - 改进模板模式判断逻辑
   - 页面加载时从API获取模式
   - 添加 `updateCurrentModeDisplay()` 函数

2. **web_app.py**
   - 完整更新所有环境变量
   - 同步更新config对象
   - 重置数据源单例

### 新增文件

1. **test_config_mode_fix.sh** - 测试脚本
2. **docs/CONFIG_MODE_FIX.md** - 本文档

## 技术细节

### 模式配置映射

| 模式 | DB_SIM_MODE | REPLAY_MODE | BINANCE_TESTNET |
|------|-------------|-------------|-----------------|
| live | 0 | 0 | 0 |
| simulation | 0 | 0 | 1 |
| backtest | 1 | 1 | 0 |

### 配置同步顺序

1. 设置环境变量
2. 更新config对象
3. 重置数据源单例
4. 返回成功响应

### JavaScript动态更新

```javascript
// 模式切换后更新显示
selectMode(mode) {
    // ... API调用 ...
    .then(data => {
        currentMode = mode;
        document.getElementById('current-mode-name').textContent = modeNames[mode];
        highlightCurrentMode();
    });
}
```

## 使用方法

### 测试模式切换

```bash
./test_config_mode_fix.sh
```

### 手动测试

1. 启动服务:
```bash
./start_web_backtest.sh
```

2. 访问配置页面:
```
http://localhost:8076/config
```

3. 点击不同模式卡片
   - 数据库回测模式
   - 模拟盘模式
   - 实盘模式

4. 观察页面顶部显示
   - 应该立即更新为选择的模式
   - 不需要刷新页面

5. 返回配置页面
   - 应该保持上次选择的模式

## 注意事项

1. **模式切换即时生效**
   - 切换后立即更新配置
   - 无需重启服务
   - 数据源自动切换

2. **数据源重置**
   - 切换模式后数据源单例重置
   - 下次API调用使用新数据源
   - 避免使用旧数据源

3. **配置持久性**
   - 仅在运行时生效
   - 重启服务后恢复默认配置
   - 如需持久化请修改环境变量或config.py

## 故障排查

### 问题1: 切换后显示还是旧的

**原因:** 页面缓存或API失败

**解决:**
```javascript
// 打开浏览器控制台查看错误
console.error('获取当前模式失败:', err);
```

### 问题2: 模式切换后K线还是从API获取

**原因:** 数据源单例未重置

**解决:**
- 检查日志中是否有 "reset_data_source"
- 刷新页面重新获取K线

## 总结

**问题已完全解决！** ✅

修复内容:
- ✅ 配置页面动态获取当前模式
- ✅ 模式切换时完整更新配置
- ✅ 数据源自动切换
- ✅ 页面显示实时更新

现在:
- ✅ 配置页面始终显示正确模式
- ✅ 切换模式后立即生效
- ✅ 返回页面保持选择模式
- ✅ 所有功能正常工作

**立即开始使用:**

```bash
./start_web_backtest.sh
```

访问: **http://localhost:8076/config** 🚀
