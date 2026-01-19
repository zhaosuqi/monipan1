# Web服务热重载功能

## 概述

Web服务现已支持代码热重载功能,在开发模式下修改代码后会自动重载服务,无需手动重启。

## 运行模式

### 1. 开发模式(默认) - 支持热重载

**功能:**
- ✅ 代码修改后自动重载
- ✅ 详细的调试信息
- ✅ 错误堆栈跟踪
- ✅ 监控关键文件变化

**监控的文件:**
- `core/config.py` - 配置文件
- `signal_module/signal_calculator.py` - 信号计算器
- `trade_module/trade_engine.py` - 交易引擎
- `trade_module/backtest_session.py` - 回测会话管理
- `data_module/db_kline_reader.py` - K线数据读取

### 2. 生产模式 - 无热重载

**功能:**
- ✅ 性能优化
- ✅ 稳定性更高
- ✅ 适合生产环境

## 使用方法

### 方法1: 使用测试脚本(推荐)

```bash
# 开发模式(默认)
python test_web_app.py

# 或明确指定
python test_web_app.py --debug
python test_web_app.py -d

# 生产模式
python test_web_app.py --prod
python test_web_app.py -p
```

### 方法2: 直接运行

```bash
# 开发模式
python web_app.py --debug
python web_app.py -d

# 生产模式
python web_app.py --prod
python web_app.py -p

# 默认模式(开发)
python web_app.py
```

### 方法3: 使用启动脚本

```bash
# 开发模式
./run_web_bigtree.sh

# 生产模式
./run_web_bigtree.sh --prod
```

## 热重载演示

### 示例1: 修改配置参数

1. 启动服务(开发模式):
```bash
python test_web_app.py
```

2. 修改配置文件 `core/config.py`:
```python
# 修改前
POSITION_BTC = 1.0

# 修改后
POSITION_BTC = 2.0
```

3. 保存文件后,服务会自动重载:
```
 * Detected change in 'core/config.py', reloading
 * Restarting with stat
 * Debugger is active!
```

4. 刷新浏览器,新配置已生效

### 示例2: 修改交易逻辑

1. 启动服务:
```bash
python test_web_app.py
```

2. 修改交易引擎 `trade_module/trade_engine.py`:
```python
# 添加新的日志
self.logger.info(f"✓ 新功能已加载")
```

3. 保存文件后自动重载

4. 重新运行回测,新逻辑生效

## 工作原理

### Flask开发模式

使用Flask的内置重载器:
- `debug=True` - 启用调试模式
- `use_reloader=True` - 启用文件监控
- `extra_files=[...]` - 额外监控的文件

### 重载流程

```
文件修改
  ↓
Werkzeug检测到变化
  ↓
停止当前进程
  ↓
重新启动进程
  ↓
重新导入所有模块
  ↓
应用新代码
```

## 注意事项

### ⚠️ 开发模式限制

1. **性能影响**:
   - 文件监控消耗资源
   - 不适合高并发场景

2. **状态不保留**:
   - 重载后会丢失内存状态
   - 回测任务会中断

3. **调试信息暴露**:
   - 错误堆栈完全显示
   - 不适合生产环境

### ✅ 生产环境部署

使用生产模式启动:
```bash
python web_app.py --prod
```

或使用专业的WSGI服务器:
```bash
gunicorn -w 4 -b 0.0.0.0:5000 web_app:app
```

## 故障排查

### 问题1: 文件修改后未重载

**原因**: 文件不在监控列表中

**解决**: 添加到 `extra_files` 列表
```python
dev_params['extra_files'].append('your_module.py')
```

### 问题2: 重载后报错

**原因**: 代码语法错误或导入错误

**解决**: 检查控制台错误信息,修复后重载会自动重试

### 问题3: 端口被占用

**原因**: 旧进程未完全关闭

**解决**:
```bash
# 查找并杀死进程
lsof -ti:5000 | xargs kill -9

# 或使用其他端口
# 修改 core/config.py
WEB_PORT = 5001
```

## 最佳实践

1. **开发时使用开发模式**
   - 快速迭代
   - 即时反馈

2. **测试时使用生产模式**
   - 模拟真实环境
   - 验证稳定性

3. **部署时使用WSGI服务器**
   - 更好的性能
   - 更好的稳定性

## 相关文件

- `web_app.py` - Web应用主文件
- `test_web_app.py` - 测试启动脚本
- `run_web_bigtree.sh` - Bash启动脚本
- `core/config.py` - 配置文件

## 监控的文件说明

| 文件 | 说明 | 修改影响 |
|------|------|----------|
| `core/config.py` | 全局配置 | 所有使用配置的地方 |
| `signal_module/signal_calculator.py` | 信号计算 | 开仓信号逻辑 |
| `trade_module/trade_engine.py` | 交易引擎 | 开仓/平仓/止盈/止损 |
| `trade_module/backtest_session.py` | 会话管理 | 回测会话划分 |
| `data_module/db_kline_reader.py` | 数据读取 | K线数据获取 |

添加更多监控文件:
```python
# 在 web_app.py 中添加
dev_params['extra_files'].extend([
    'your_module/your_file.py',
    'another_module/file.py',
])
```

## 技术栈

- **Flask** - Web框架
- **Flask-SocketIO** - WebSocket支持
- **Werkzeug** - 文件监控重载器
- **Lightweight Charts** - K线图表
- **Bootstrap** - UI框架
